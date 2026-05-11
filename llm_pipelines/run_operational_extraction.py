"""
OPERATIONAL extraction entry point. Thin wrapper over disclosure_runner.

Run: uv run python -m llm_pipelines.run_operational_extraction
     uv run python -m llm_pipelines.run_operational_extraction --iata LHR LGW
     uv run python -m llm_pipelines.run_operational_extraction --force
"""

import argparse
import logging

from backend.db.connection import SessionLocal
from llm_pipelines.disclosure_runner import INTER_CALL_SLEEP_SECONDS, run_disclosures
from llm_pipelines.operational_extraction import OperationalExtractionPipeline

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from dotenv import load_dotenv
    load_dotenv(override=True)

    parser = argparse.ArgumentParser()
    parser.add_argument("--iata", nargs="*", help="Filter to specific IATA codes (default: all)")
    parser.add_argument("--force", action="store_true",
                        help="Skip the content-hash cache and re-call the LLM")
    parser.add_argument("--no-throttle", action="store_true",
                        help="Disable inter-call rate-limit sleep (use sparingly)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = run_disclosures(
            db,
            pipeline=OperationalExtractionPipeline(),
            iatas=args.iata,
            force=args.force,
            inter_call_sleep_seconds=0 if args.no_throttle else INTER_CALL_SLEEP_SECONDS,
        )
        print(
            f"Operational extraction: "
            f"created={result['created']} skipped={result['skipped']} "
            f"auto_approved={result['auto_approved']} pending_review={result['pending_review']} "
            f"errors={result['errors']} failures={result['failures']}"
        )
    finally:
        db.close()
