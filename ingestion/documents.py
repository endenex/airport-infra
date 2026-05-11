"""
Document fetch + storage helpers for LLM-extraction pipelines.

Downloads a PDF (or other binary doc) once, stores it in R2 keyed by
content hash, and returns text content for LLM consumption. Idempotent:
re-fetching the same URL twice incurs one HTTP round-trip; the R2 PUT is
skipped on the second call.
"""

import io
import logging
from dataclasses import dataclass

import httpx
from pypdf import PdfReader

from backend import storage

logger = logging.getLogger(__name__)


@dataclass
class FetchedDocument:
    """A document that's been downloaded, hashed, and stored in R2."""

    source_url: str
    source_id: str
    content_hash: str        # sha256 hex; also the document_id in R2
    r2_key: str
    content_bytes: bytes
    content_type: str
    size_bytes: int


def fetch_and_store(
    url: str,
    source_id: str,
    *,
    timeout: float = 120.0,
    # Mozilla-compatible preamble so gov / regulator sites (e.g. transportes.gob.es)
    # don't return 403 to UAs without it. Identification suffix still tells
    # the operator who we are.
    user_agent: str = (
        "Mozilla/5.0 (compatible; airport-infra-platform/1.0; alex@endenex.com)"
    ),
) -> FetchedDocument:
    """
    Download a document, content-hash it, upload to R2 if new.

    R2 key layout: {source_id}/{sha256}. Same content → same key, so re-runs
    are free. Returns the bytes regardless (callers usually need them
    immediately for text extraction).
    """
    headers = {"User-Agent": user_agent}
    resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()

    content = resp.content
    content_hash = storage.content_hash(content)
    content_type = resp.headers.get("content-type", "application/octet-stream").split(";")[0].strip()

    if storage.document_exists(source_id, content_hash):
        r2_key = storage.document_key(source_id, content_hash)
        logger.info("R2 already has %s (%d bytes) — skip upload", r2_key, len(content))
    else:
        r2_key = storage.upload_document(content, source_id, content_hash, content_type=content_type)

    return FetchedDocument(
        source_url=url,
        source_id=source_id,
        content_hash=content_hash,
        r2_key=r2_key,
        content_bytes=content,
        content_type=content_type,
        size_bytes=len(content),
    )


def extract_pdf_text(content: bytes, max_chars: int | None = None) -> str:
    """
    Extract plain text from a PDF. Page boundaries marked with form-feed (\\f)
    so downstream consumers can split if needed. Optionally truncate to
    max_chars (useful when feeding to a context-limited model).
    """
    reader = PdfReader(io.BytesIO(content))
    pages = []
    for i, page in enumerate(reader.pages):
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:
            logger.warning("pypdf failed on page %d: %s", i, exc)
            pages.append("")
    text = "\f".join(pages)
    if max_chars is not None and len(text) > max_chars:
        logger.info("Truncating PDF text from %d to %d chars", len(text), max_chars)
        text = text[:max_chars]
    return text


def extract_html_text(content: bytes, max_chars: int | None = None) -> str:
    """
    Extract visible text from HTML. Strips script/style, collapses whitespace,
    keeps paragraph structure with double newlines. Used for press releases
    that aren't published as PDFs.
    """
    from lxml import html as lxml_html  # already a dependency via XBRL ingestor

    try:
        doc = lxml_html.fromstring(content)
    except Exception as exc:
        logger.warning("HTML parse failed: %s", exc)
        return ""
    # Drop noise
    for el in doc.xpath("//script|//style|//nav|//footer|//header|//noscript"):
        el.getparent().remove(el)
    # text_content() concatenates everything; we collapse whitespace.
    raw = doc.text_content()
    # Normalise: split on whitespace, rejoin with single spaces per line; then
    # collapse 3+ newlines to 2 to preserve paragraph breaks.
    lines = [line.strip() for line in raw.splitlines()]
    lines = [line for line in lines if line]
    text = "\n\n".join(lines)
    if max_chars is not None and len(text) > max_chars:
        logger.info("Truncating HTML text from %d to %d chars", len(text), max_chars)
        text = text[:max_chars]
    return text


def extract_text_from_document(fetched: "FetchedDocument", max_chars: int | None = None) -> str:
    """
    Auto-route to PDF or HTML extractor based on content_type. Used by
    pipelines that need to handle either kind of source (transaction press
    releases, regulatory consent docs).
    """
    ct = (fetched.content_type or "").lower()
    if "pdf" in ct:
        return extract_pdf_text(fetched.content_bytes, max_chars=max_chars)
    if "html" in ct or "xhtml" in ct:
        return extract_html_text(fetched.content_bytes, max_chars=max_chars)
    # Fallback: try PDF first (file might have wrong content-type)
    try:
        return extract_pdf_text(fetched.content_bytes, max_chars=max_chars)
    except Exception:
        return extract_html_text(fetched.content_bytes, max_chars=max_chars)
