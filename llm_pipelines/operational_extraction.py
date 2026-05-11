"""
OPERATIONAL extraction pipeline.

Pulls structured traffic statistics — passengers, aircraft movements,
cargo — from an airport operator's annual or sustainability report.
Returns one ExtractedRecord per (concept, period) pair with a confidence
score; identity-only fields in payload, evidence text in raw_llm_response.

Confidence routing (from LLMPipelineBase): score >= 0.85 → auto_approved,
< 0.85 → pending_review.
"""

import json
import logging
from datetime import datetime, timezone

from llm_pipelines.base import ExtractedRecord, LLMPipelineBase
from llm_pipelines.climate_extraction import _parse_response_json  # same JSON envelope

logger = logging.getLogger(__name__)


# Stable concept keys. These live in DataRecord.payload.concept and
# downstream queries depend on them — keep them terse and don't rename.
OPERATIONAL_CONCEPTS = [
    "passengers_total",
    "passengers_domestic",
    "passengers_international",
    "passengers_transfer",
    "air_transport_movements",
    "aircraft_movements_total",
    "cargo_tonnes",
]


SYSTEM_PROMPT = """You are extracting structured operational traffic statistics from an airport operator's annual or sustainability report.

Return ONLY a JSON object (no prose, no markdown fences) with this exact schema:
{
  "extractions": [
    {
      "concept": "<one of the allowed concepts below>",
      "value": <number — count for passenger/movement concepts; tonnes for cargo>,
      "unit": "passengers" | "movements" | "tonnes",
      "period_start": "YYYY-MM-DD" | null,
      "period_end": "YYYY-MM-DD",
      "confidence": <float 0.0-1.0>,
      "evidence_quote": "<verbatim or near-verbatim sentence from the document supporting this value>"
    }
  ]
}

Allowed concepts:
- passengers_total                — total annual passengers (terminal pax). All-traffic figure.
- passengers_domestic             — domestic-route passengers only.
- passengers_international        — international-route passengers only.
- passengers_transfer             — transfer / connecting passengers (relevant for hub airports).
- air_transport_movements         — commercial flight movements (ATMs), one movement = one take-off or one landing.
- aircraft_movements_total        — TOTAL aircraft movements including non-commercial (general aviation, military, etc).
- cargo_tonnes                    — freight tonnage (excluding mail unless the document explicitly combines them).

Rules:
- Extract ONLY values that are explicitly stated in the document. Do not infer, estimate, or sum.
- Numeric values must be the raw count (e.g. 79_212_440 passengers, NOT "79.2 million"). If the document uses "79.2m" or "79.2 million", convert to the integer.
- Each concept may appear multiple times if the document reports comparative years (e.g. current + prior year).
- For "movements": prefer the specific concept (air_transport_movements vs aircraft_movements_total) the document actually labels. If only one is given without qualification, use aircraft_movements_total.
- For cargo: tonnes only. Skip if reported in different units without conversion in the document.
- Confidence rubric:
  - 0.95+ : value is explicit in a numeric table, period is unambiguous, units are clear
  - 0.85-0.94 : value is explicit but minor interpretation needed (e.g. "approximately", taken from a chart label, period inferred from report context)
  - 0.70-0.84 : value present but notable ambiguity (rounded headline figure, restated, unclear scope)
  - <0.70 : significant uncertainty — explain in evidence_quote
- evidence_quote MUST be a real sentence/fragment from the source. Do not paraphrase.
- If a concept is not reported, omit it. Do not emit nulls or zero placeholders.
"""


class OperationalExtractionPipeline(LLMPipelineBase):
    """Extracts traffic-statistic KPIs from an airport operator disclosure document."""

    prompt_version = "1.0"
    record_type = "OPERATIONAL"

    def build_messages(self, document: str, context: dict) -> list[dict]:
        """
        context expects:
          - entity_name: str
          - source_url: str
          - source_document_id: str (content hash)
          - reporting_period_end: str (YYYY-MM-DD, the report's primary period)
        """
        user_msg = (
            f"Source: {context.get('entity_name', '<unknown>')} disclosure document\n"
            f"Reporting period end: {context.get('reporting_period_end', '<unknown>')}\n"
            f"Source URL: {context.get('source_url', '<unknown>')}\n\n"
            f"Document text:\n---\n{document}\n---\n\n"
            "Return the JSON object now."
        )
        return [
            {"role": "user", "content": [{"type": "text", "text": SYSTEM_PROMPT + "\n\n" + user_msg}]},
        ]

    def parse_response(self, response_text: str, context: dict) -> list[ExtractedRecord]:
        try:
            parsed = _parse_response_json(response_text)
        except json.JSONDecodeError as exc:
            logger.error("LLM response not valid JSON: %s — raw: %s", exc, response_text[:500])
            return []

        retrieved_at = datetime.now(timezone.utc)
        records: list[ExtractedRecord] = []
        entity_key_prefix = context.get("entity_key_prefix", "unknown")
        airport_id = context.get("airport_id")

        for item in parsed.get("extractions", []):
            concept = item.get("concept")
            if concept not in OPERATIONAL_CONCEPTS:
                logger.warning("Dropping out-of-allowlist concept: %r", concept)
                continue

            try:
                value = float(item["value"])
            except (KeyError, TypeError, ValueError):
                logger.warning("Dropping extraction with non-numeric value: %r", item)
                continue
            # Operational counts are always positive — guard against the model
            # emitting a negative or zero placeholder.
            if value <= 0:
                logger.warning("Dropping non-positive operational value: %r", item)
                continue

            confidence = item.get("confidence")
            try:
                confidence = float(confidence)
                confidence = max(0.0, min(1.0, confidence))
            except (TypeError, ValueError):
                confidence = 0.0

            period_end = item.get("period_end")
            period_start = item.get("period_start")

            entity_key = f"{entity_key_prefix}:{concept}:{period_end}"

            # payload holds ONLY identifying fields — it's hashed into the
            # deterministic record ID, so any field that can vary across runs
            # (e.g. evidence_quote wording from the LLM, even at temp=0)
            # belongs in raw_llm_response, not here.
            records.append(
                ExtractedRecord(
                    entity_key=entity_key,
                    source_url=context["source_url"],
                    source_document_id=context.get("source_document_id"),
                    retrieved_at=retrieved_at,
                    record_type="OPERATIONAL",
                    period_start=period_start,
                    period_end=period_end,
                    airport_id=airport_id,
                    payload={
                        "entity_name": context.get("entity_name"),
                        "concept": concept,
                        "value": value,
                        "unit": item.get("unit"),
                    },
                    confidence_score=confidence,
                    raw_llm_response=item,
                )
            )

        logger.info(
            "Parsed %d operational extractions (%d concepts represented)",
            len(records),
            len({r.payload["concept"] for r in records}),
        )
        return records
