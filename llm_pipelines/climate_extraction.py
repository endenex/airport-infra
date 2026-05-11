"""
CLIMATE extraction pipeline.

Pulls structured climate disclosures (Scope 1/2/3 emissions, renewable
energy share, net-zero target year) from an airport operator's annual
or sustainability report. Returns one ExtractedRecord per (concept, period)
pair, each with a confidence score, an evidence quote, and the page hint.

Confidence routing (from LLMPipelineBase): score >= 0.85 → auto_approved,
< 0.85 → pending_review.
"""

import json
import logging
import re
from datetime import datetime, timezone

from llm_pipelines.base import ExtractedRecord, LLMPipelineBase

logger = logging.getLogger(__name__)


# Concepts we extract. Keeping the keys terse and stable — they live in
# DataRecord.payload.concept, so downstream queries depend on them.
CLIMATE_CONCEPTS = [
    "scope_1_emissions_tco2e",
    "scope_2_emissions_location_based_tco2e",
    "scope_2_emissions_market_based_tco2e",
    "scope_3_emissions_tco2e",
    "total_emissions_tco2e",
    "renewable_energy_percent",
    "net_zero_target_year",
]


SYSTEM_PROMPT = """You are extracting structured climate disclosures from an airport operator's annual or sustainability report.

Return ONLY a JSON object (no prose, no markdown fences) with this exact schema:
{
  "extractions": [
    {
      "concept": "<one of the allowed concepts below>",
      "value": <number — emissions in tCO2e, percent as 0-100, year as YYYY>,
      "unit": "tCO2e" | "percent" | "year",
      "period_start": "YYYY-MM-DD" | null,
      "period_end": "YYYY-MM-DD",
      "confidence": <float 0.0-1.0>,
      "evidence_quote": "<verbatim or near-verbatim sentence from the document supporting this value>"
    }
  ]
}

Allowed concepts:
- scope_1_emissions_tco2e
- scope_2_emissions_location_based_tco2e
- scope_2_emissions_market_based_tco2e
- scope_3_emissions_tco2e
- total_emissions_tco2e
- renewable_energy_percent
- net_zero_target_year

Rules:
- Extract ONLY values that are explicitly stated in the document. Do not infer or estimate.
- Each concept may appear multiple times if the document reports it for multiple periods (e.g. current year + comparative year).
- For Scope 2: emit a separate row for location-based and market-based if both are reported. If only one method is reported, label it accordingly.
- For total emissions: only emit if the document gives a TOTAL Scope 1+2+3 (don't sum components yourself).
- Confidence rubric:
  - 0.95+ : value is explicit, period is unambiguous, units are clear
  - 0.85-0.94 : value is explicit but minor interpretation needed (e.g. taken from a chart axis label, period inferred from report context)
  - 0.70-0.84 : value is present but with notable ambiguity (estimate, restated figure, unclear period)
  - <0.70 : significant uncertainty — explain in evidence_quote
- evidence_quote MUST be a real sentence/fragment from the source. Do not paraphrase.
- If a concept is not reported, omit it. Do not emit nulls or zero placeholders.
"""


def _parse_response_json(response_text: str) -> dict:
    """
    Parse the model's JSON response. Strips any code-fence markers and
    extracts the first {...} block if the model wraps the JSON.
    """
    text = response_text.strip()
    # Strip ```json ... ``` or ``` ... ``` fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # Extract the first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


class ClimateExtractionPipeline(LLMPipelineBase):
    """Extracts climate KPIs from an airport operator disclosure document."""

    prompt_version = "1.0"

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
            if concept not in CLIMATE_CONCEPTS:
                logger.warning("Dropping out-of-allowlist concept: %r", concept)
                continue

            try:
                value = float(item["value"])
            except (KeyError, TypeError, ValueError):
                logger.warning("Dropping extraction with non-numeric value: %r", item)
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
                    record_type="CLIMATE",
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
                    raw_llm_response=item,  # contains evidence_quote, model's exact reply
                )
            )

        logger.info(
            "Parsed %d climate extractions (%d concepts represented)",
            len(records),
            len({r.payload["concept"] for r in records}),
        )
        return records
