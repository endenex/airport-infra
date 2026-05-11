"""
CLI runner for transaction extraction from a press release URL.

Fetches the URL (PDF or HTML), stores in R2 keyed by content hash,
extracts text, runs the LLM, writes one Transaction row.

Run:
  uv run python -m llm_pipelines.run_transaction_extraction \\
      --url https://example.com/press-release \\
      --source-id vinci_press
"""

import argparse
import logging

from backend.db.connection import SessionLocal
from ingestion.documents import extract_text_from_document, fetch_and_store
from llm_pipelines.transaction_extraction import TransactionExtractionPipeline

logger = logging.getLogger(__name__)

# Press releases are typically short; keep input under the Haiku 4.5
# per-minute rate-limit window with headroom for the prompt.
MAX_DOC_CHARS = 150_000


def run(url: str, source_id: str) -> dict:
    fetched = fetch_and_store(url, source_id=source_id)
    logger.info(
        "Fetched %s: %.1fKB, content_type=%s, hash=%s",
        url, fetched.size_bytes / 1_000, fetched.content_type, fetched.content_hash[:12],
    )

    text = extract_text_from_document(fetched, max_chars=MAX_DOC_CHARS)
    logger.info("Extracted %d chars of text", len(text))

    pipeline = TransactionExtractionPipeline()
    extraction = pipeline.extract(text, source_url=url)
    logger.info(
        "LLM extracted: state=%s type=%s asset=%r confidence=%.2f",
        extraction.parsed.get("state"),
        extraction.parsed.get("transaction_type"),
        extraction.parsed.get("asset_name", "")[:60],
        extraction.overall_confidence,
    )

    db = SessionLocal()
    try:
        row = pipeline.persist(
            db, extraction,
            source_url=url,
            source_document_id=fetched.content_hash,
        )
        logger.info(
            "Persisted transaction id=%s state=%s asset=%r",
            row.id, row.state, row.asset_name[:80],
        )
        return {
            "id": str(row.id),
            "state": row.state,
            "asset_name": row.asset_name,
            "buyer_count": len(row.buyer_entities or []),
            "seller_count": len(row.seller_entities or []),
            "rival_count": len(row.rival_bids or []),
            "overall_confidence": extraction.overall_confidence,
        }
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from dotenv import load_dotenv
    load_dotenv(override=True)

    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Press release / consent doc URL")
    parser.add_argument(
        "--source-id", default="press_release",
        help="Source namespace for R2 storage (e.g. 'vinci_press', 'cma_decisions')",
    )
    args = parser.parse_args()

    result = run(args.url, args.source_id)
    print(
        f"\nTransaction extracted:\n"
        f"  id:                 {result['id']}\n"
        f"  state:              {result['state']}\n"
        f"  asset:              {result['asset_name']}\n"
        f"  buyers/sellers/rivals: {result['buyer_count']}/{result['seller_count']}/{result['rival_count']}\n"
        f"  overall_confidence: {result['overall_confidence']:.2f}"
    )
