"""
Transaction extraction pipeline — LLM-from-press-release → transactions table.

Takes a press release / CMA decision / sponsor disclosure document, extracts
one Transaction record, writes it to the transactions table with full
provenance.

Honesty discipline (Appendix D #19, locked):
  - identifier_status="identified" ONLY when the document explicitly names
    a party as confirmed. "rumoured" / "reportedly" / "said to be" / press
    leak → "suspected". Unattributed mentions → "unknown".
  - price_information_confidence="confirmed" only when a numeric value is
    explicitly stated. Press-leak attribution → "rumored". Range stated
    without specific figure → "range". Silent → "unknown".
  - state="closed" only when document confirms completion. "abandoned" /
    "pulled" / "postponed" only when document confirms it. Entire deal
    press-leak-only → "rumored".

Not a subclass of LLMPipelineBase: that base writes to data_records +
llm_extractions. Transactions live in their own table with their own
field-level confidence flags, so the persist path is different. Same
spirit (deterministic temp=0, JSON envelope) but a focused implementation.
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import Airport, MethodologyVersion
from backend.models.transaction import (
    VALID_FAILURE_STATUS,
    VALID_PRICE_CONFIDENCE,
    VALID_STATES,
    VALID_TRANSACTION_TYPES,
    Transaction,
)

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are extracting one airport-infrastructure transaction from a press release, regulatory consent decision, or sponsor disclosure document.

Return ONLY a JSON object (no prose, no markdown fences) with this exact schema:
{
  "transaction": {
    "asset_name": "<concise human-readable name of what's being transacted>",
    "iata_hint": "<3-letter IATA code if the document mentions one>" | null,
    "state": "closed" | "abandoned" | "pulled" | "bid_lost" | "postponed" | "rumored",
    "transaction_type": "acquisition" | "divestment" | "refinancing" | "ipo" | "concession_award" | "minority_stake" | "secondary_buyout" | "other",
    "announce_date": "YYYY-MM-DD" | null,
    "signing_date": "YYYY-MM-DD" | null,
    "close_date": "YYYY-MM-DD" | null,
    "enterprise_value": <number> | null,
    "equity_value": <number> | null,
    "currency": "GBP" | "EUR" | "USD" | "..." | null,
    "stake_percent": <number 0-100> | null,
    "price_information_confidence": "confirmed" | "rumored" | "range" | "unknown",
    "reason_for_failure_status": "disclosed" | "inferred" | "unknown" | null,
    "reason_for_failure_text": "<one-paragraph explanation if state != closed>" | null,
    "buyer_entities": [
      {
        "name": "<entity name>",
        "role": "lead" | "co_investor" | "lp" | "advisor",
        "identifier_status": "identified" | "suspected" | "unknown",
        "equity_stake_pct": <number 0-100> | null,
        "is_strategic_operator": true | false | null,
        "fund_name": "<fund vehicle name if disclosed>" | null,
        "fund_vintage": <YYYY integer if disclosed> | null,
        "source_quote": "<verbatim sentence from the doc that names this party>"
      }
    ],
    "seller_entities": [ /* same shape as buyer_entities */ ],
    "rival_bids": [
      {
        "name": "<bidder name>",
        "identifier_status": "identified" | "suspected" | "unknown",
        "bid_price": <number> | null,
        "price_confidence": "confirmed" | "rumored" | "range" | "unknown",
        "outcome": "lost" | "withdrew" | "shortlisted" | "unknown",
        "source_quote": "<verbatim sentence from the doc>"
      }
    ],
    "overall_extraction_confidence": <float 0.0-1.0>,
    "evidence_summary": "<two-sentence summary of what the doc actually says>"
  }
}

Rules — these are non-negotiable:

1. **State of the transaction.** "closed" only if the document confirms completion (signed and closed). "abandoned"/"pulled"/"postponed" only with explicit confirmation. "rumored" if the entire deal is press-leak only.

2. **Party attribution.** A party's identifier_status MUST reflect document tone:
   - "identified": document names them as a confirmed party (buyer, seller, lender)
   - "suspected": document hedges ("rumoured", "reportedly", "according to sources", "said to be among interested parties")
   - "unknown": document references an unnamed party ("a sovereign wealth fund", "two unnamed bidders")

3. **Price confidence.** "confirmed" requires the document to state the number explicitly as fact. "rumored" if the number comes from press leaks the doc cites. "range" if the doc gives "£2-3bn" or similar. "unknown" if no number stated.

4. **Rival bidders.** A rival_bid entry is a party that was at the table but did not win — losing bids, withdrawn bids, shortlisted-but-not-selected. ONLY include rival bidders that the document actually names or hedges; never invent.

5. **No inference, no synthesis.** Do not compute enterprise_value from stake_percent × equity_value. Do not name a "likely sponsor" the document doesn't mention.

6. **evidence_summary** is two sentences max. State what the document says, not your interpretation.

7. **overall_extraction_confidence** reflects your confidence the document supports the extracted transaction shape. High (0.9+) for explicit press releases with all key fields; moderate (0.7-0.9) for partial coverage; low (<0.7) for ambiguous or press-leak-only documents.
"""


# ── Output container ────────────────────────────────────────────────────


@dataclass
class TransactionExtraction:
    """Result of one extraction — raw parsed payload + the model's overall confidence."""

    parsed: dict
    overall_confidence: float
    evidence_summary: str
    raw_response: dict


# ── JSON helpers (reused from climate parser) ───────────────────────────


def _parse_response_json(response_text: str) -> dict:
    text = response_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _resolve_airport_id(db: Session, iata_hint: str | None) -> uuid.UUID | None:
    if not iata_hint or len(iata_hint) != 3:
        return None
    airport = db.scalar(select(Airport).where(Airport.iata_code == iata_hint.upper()))
    return airport.id if airport else None


def _coerce_party_list(raw: list | None) -> list[dict] | None:
    """Validate and normalise each party entry. Drops entries missing 'name'."""
    if not raw:
        return None
    cleaned: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if not entry.get("name"):
            continue
        status = entry.get("identifier_status", "unknown")
        if status not in ("identified", "suspected", "unknown"):
            status = "unknown"
        entry["identifier_status"] = status
        cleaned.append(entry)
    return cleaned or None


# ── The pipeline ────────────────────────────────────────────────────────


class TransactionExtractionPipeline:
    prompt_version = "1.0"
    temperature = 0.0
    max_tokens = 4096

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self.client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def extract(self, document_text: str, source_url: str) -> TransactionExtraction:
        user_msg = (
            f"Source URL: {source_url}\n\n"
            f"Document text:\n---\n{document_text}\n---\n\n"
            "Return the JSON object now."
        )
        response = self.client.messages.create(
            model=settings.llm_extraction_model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[
                {"role": "user",
                 "content": [{"type": "text", "text": SYSTEM_PROMPT + "\n\n" + user_msg}]},
            ],
        )
        first_block = response.content[0]
        response_text = getattr(first_block, "text", None)
        if response_text is None:
            raise RuntimeError(f"Expected text block, got {type(first_block).__name__}")
        parsed = _parse_response_json(response_text)
        txn = parsed.get("transaction") or {}
        return TransactionExtraction(
            parsed=txn,
            overall_confidence=float(txn.get("overall_extraction_confidence", 0.0)),
            evidence_summary=str(txn.get("evidence_summary", "")),
            raw_response=parsed,
        )

    def persist(
        self,
        db: Session,
        extraction: TransactionExtraction,
        *,
        source_url: str,
        source_document_id: str | None,
        ingestion_run_id: uuid.UUID | None = None,
    ) -> Transaction:
        """
        Write the parsed transaction into the transactions table with full
        provenance. Validates lexicons (state / transaction_type / etc.)
        against the canonical sets — a hallucinated value falls back to a
        safe default ("other", "unknown") and is logged.
        """
        txn = extraction.parsed
        if not txn:
            raise ValueError("Extraction had no 'transaction' payload")

        state = txn.get("state", "rumored")
        if state not in VALID_STATES:
            logger.warning("LLM returned invalid state %r; falling back to 'rumored'", state)
            state = "rumored"

        txn_type = txn.get("transaction_type", "other")
        if txn_type not in VALID_TRANSACTION_TYPES:
            logger.warning("LLM returned invalid transaction_type %r; falling back to 'other'", txn_type)
            txn_type = "other"

        price_conf = txn.get("price_information_confidence")
        if price_conf is not None and price_conf not in VALID_PRICE_CONFIDENCE:
            price_conf = "unknown"

        failure_status = txn.get("reason_for_failure_status")
        if failure_status is not None and failure_status not in VALID_FAILURE_STATUS:
            failure_status = "unknown"

        airport_id = _resolve_airport_id(db, txn.get("iata_hint"))

        mv = db.scalar(
            select(MethodologyVersion).order_by(MethodologyVersion.effective_from.asc())
        )
        if mv is None:
            raise RuntimeError("No methodology version configured; run migrations first")

        # The pipeline's overall extraction confidence + the LLM's evidence
        # summary go into notes for the row. Field-level confidence (price,
        # identifier_status per party) is preserved on the row directly.
        notes = (
            f"Extracted by transaction_extraction.py prompt v{self.prompt_version}; "
            f"overall_confidence={extraction.overall_confidence:.2f}.\n\n"
            f"Evidence summary: {extraction.evidence_summary}"
        )

        row = Transaction(
            airport_id=airport_id,
            asset_name=txn.get("asset_name", "")[:500] or "<unknown asset>",
            announce_date=_parse_date(txn.get("announce_date")),
            signing_date=_parse_date(txn.get("signing_date")),
            close_date=_parse_date(txn.get("close_date")),
            state=state,
            transaction_type=txn_type,
            enterprise_value=txn.get("enterprise_value"),
            equity_value=txn.get("equity_value"),
            currency=txn.get("currency"),
            stake_percent=txn.get("stake_percent"),
            price_information_confidence=price_conf,
            reason_for_failure_status=failure_status,
            reason_for_failure_text=txn.get("reason_for_failure_text"),
            buyer_entities=_coerce_party_list(txn.get("buyer_entities")),
            seller_entities=_coerce_party_list(txn.get("seller_entities")),
            rival_bids=_coerce_party_list(txn.get("rival_bids")),
            source_url=source_url,
            source_document_id=source_document_id,
            retrieved_at=datetime.now(timezone.utc),
            methodology_version_id=mv.id,
            ingestion_run_id=ingestion_run_id,
            notes=notes,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
