"""
CONCESSION extraction pipeline.

Pulls structured regulatory-economics KPIs from an airport price-control
decision (CAA H7, AENA DORA, ADP CRE, etc.). These are the numbers an IC
paper needs to value a regulated airport: allowed cost of capital,
regulated asset base, traffic forecasts, capex envelope, allowed yield.

Concept allowlist is numeric only. Constant per-document metadata
(regulator name, framework name, regulatory period bounds) is carried
through context from the Disclosure registry — not asked of the LLM —
so it can't drift or hallucinate.

Confidence routing (from LLMPipelineBase): score >= 0.85 → auto_approved,
< 0.85 → pending_review.
"""

import json
import logging
from datetime import datetime, timezone

from llm_pipelines.base import ExtractedRecord, LLMPipelineBase
from llm_pipelines.climate_extraction import _parse_response_json  # same envelope

logger = logging.getLogger(__name__)


# Stable concept keys. These live in DataRecord.payload.concept; downstream
# queries depend on them. Keep terse; don't rename.
#
# Period semantics:
#   - "period_scope" = "regulatory_period"   → record covers full reg period
#                                              (e.g. H7: 2022-2026)
#   - "period_scope" = "annual"              → one record per regulatory year,
#                                              period_start/end set to that year
CONCESSION_CONCEPTS = {
    # Period-scoped (one record per regulatory period)
    "allowed_wacc_real_pretax_pct": "regulatory_period",
    "allowed_wacc_nominal_pretax_pct": "regulatory_period",
    "allowed_wacc_vanilla_pct": "regulatory_period",
    "regulated_asset_base_opening_gbp_million": "regulatory_period",
    "regulated_asset_base_closing_gbp_million": "regulatory_period",
    "capex_allowance_total_gbp_million": "regulatory_period",
    # Annual (one record per regulatory year)
    "forecast_passengers_pax": "annual",
    "allowed_yield_per_pax_gbp": "annual",
    "forecast_capex_gbp_million": "annual",
    "forecast_opex_gbp_million": "annual",
}


SYSTEM_PROMPT = """You are extracting structured regulatory-economics numbers from an airport price-control decision document (e.g. CAA H7, AENA DORA, ADP CRE).

Return ONLY a JSON object (no prose, no markdown fences) with this exact schema:
{
  "extractions": [
    {
      "concept": "<one of the allowed concepts below>",
      "value": <number — see units below>,
      "unit": "percent" | "GBP_million" | "GBP_per_pax" | "passengers",
      "period_start": "YYYY-MM-DD" | null,
      "period_end": "YYYY-MM-DD",
      "confidence": <float 0.0-1.0>,
      "evidence_quote": "<verbatim or near-verbatim sentence from the document>"
    }
  ]
}

Allowed concepts (period_scope shown — leave period_start null only when
the value covers the entire regulatory period as a single figure):

  Period-scoped (one record covering the full regulatory period):
    allowed_wacc_real_pretax_pct                   unit "percent"
    allowed_wacc_nominal_pretax_pct                unit "percent"
    allowed_wacc_vanilla_pct                       unit "percent"
    regulated_asset_base_opening_gbp_million       unit "GBP_million"  (start of period)
    regulated_asset_base_closing_gbp_million       unit "GBP_million"  (end of period)
    capex_allowance_total_gbp_million              unit "GBP_million"  (cumulative over period)

  Annual (one record per regulatory year — set period_start and period_end to that year):
    forecast_passengers_pax                        unit "passengers"
    allowed_yield_per_pax_gbp                      unit "GBP_per_pax"
    forecast_capex_gbp_million                     unit "GBP_million"
    forecast_opex_gbp_million                      unit "GBP_million"

Rules:
- Extract ONLY values that are explicitly stated in the document. Do not infer, estimate, or compute.
- WACC variants are distinct concepts — do NOT merge "real" and "nominal", or "pre-tax" and "post-tax". If only one variant is given, emit only that one.
- Currency: figures expressed in GBP only (millions). If the document is in another currency, skip — do not convert.
- "GBP_million" means actual £ million (e.g. 17000 means £17 billion).
- For annual concepts: if the document presents a 5-year forecast table, emit ONE record per regulatory year.
- For percent concepts: express as 0-100 (so 5.6% is value=5.6, not 0.056).
- Confidence rubric:
  - 0.95+ : value explicit in a numeric table or headline statement, unambiguous units
  - 0.85-0.94 : value explicit but with minor interpretation needed (chart label, footnoted)
  - 0.70-0.84 : value present but with notable ambiguity (range stated, "approximately", restated)
  - <0.70 : significant uncertainty — explain in evidence_quote
- evidence_quote MUST be a real sentence/fragment from the source.
- If a concept is not stated, omit it. Do not emit nulls or placeholders.
"""


class ConcessionExtractionPipeline(LLMPipelineBase):
    """Extracts regulatory-economics KPIs from a price-control decision document."""

    prompt_version = "1.0"
    record_type = "CONCESSION"

    def build_messages(self, document: str, context: dict) -> list[dict]:
        regulator = context.get("regulator_name", "<unknown regulator>")
        framework = context.get("regulatory_framework_name", "<unknown framework>")
        reg_start = context.get("regulatory_period_start", "<unknown>")
        reg_end = context.get("regulatory_period_end", "<unknown>")
        user_msg = (
            f"Source: {context.get('entity_name', '<unknown>')} regulatory decision\n"
            f"Regulator: {regulator}\n"
            f"Framework: {framework}\n"
            f"Regulatory period: {reg_start} to {reg_end}\n"
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
        regulator = context.get("regulator_name")
        framework = context.get("regulatory_framework_name")
        reg_start = context.get("regulatory_period_start")
        reg_end = context.get("regulatory_period_end")

        for item in parsed.get("extractions", []):
            concept = item.get("concept")
            if concept not in CONCESSION_CONCEPTS:
                logger.warning("Dropping out-of-allowlist concept: %r", concept)
                continue

            try:
                value = float(item["value"])
            except (KeyError, TypeError, ValueError):
                logger.warning("Dropping non-numeric value: %r", item)
                continue

            confidence = item.get("confidence")
            try:
                confidence = max(0.0, min(1.0, float(confidence)))
            except (TypeError, ValueError):
                confidence = 0.0

            # period_scope tells us whether the LLM-supplied period is for an
            # annual slice or the full regulatory period. We trust the LLM's
            # period for "annual" concepts; for "regulatory_period" concepts
            # we override with the Disclosure-level period bounds.
            scope = CONCESSION_CONCEPTS[concept]
            if scope == "regulatory_period":
                period_start = reg_start
                period_end = reg_end
            else:  # annual
                period_start = item.get("period_start")
                period_end = item.get("period_end")
                if not period_end:
                    logger.warning("Annual concept missing period_end: %r", item)
                    continue

            entity_key = f"{entity_key_prefix}:{concept}:{period_end}"

            # payload holds identity-only fields.  Per-document metadata
            # (regulator, framework) IS identity here — different frameworks
            # for the same airport (H7 vs Q5+ vs H8) should produce distinct
            # records, so they enter the hash.
            payload = {
                "entity_name": context.get("entity_name"),
                "concept": concept,
                "value": value,
                "unit": item.get("unit"),
                "regulator_name": regulator,
                "regulatory_framework_name": framework,
            }

            records.append(
                ExtractedRecord(
                    entity_key=entity_key,
                    source_url=context["source_url"],
                    source_document_id=context.get("source_document_id"),
                    retrieved_at=retrieved_at,
                    record_type="CONCESSION",
                    period_start=period_start,
                    period_end=period_end,
                    airport_id=airport_id,
                    payload=payload,
                    confidence_score=confidence,
                    raw_llm_response=item,
                )
            )

        logger.info(
            "Parsed %d concession extractions (%d concepts represented)",
            len(records),
            len({r.payload["concept"] for r in records}),
        )
        return records
