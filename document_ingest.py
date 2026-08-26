"""
Extract text from uploaded PDF policy documents.
"""

from __future__ import annotations

import logging
import re
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Union

from pypdf import PdfReader

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 15 * 1024 * 1024  # 15 MB per file


def _normalize_whitespace(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_text_from_pdf(source: Union[bytes, BinaryIO, Path, str]) -> str:
    """
    Extract plain text from a PDF file or bytes.

    Raises:
        ValueError: If the PDF is empty, unreadable, or yields no text.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.stat().st_size > MAX_PDF_BYTES:
            raise ValueError(f"PDF exceeds maximum size of {MAX_PDF_BYTES // (1024 * 1024)} MB.")
        reader = PdfReader(str(path))
    elif isinstance(source, bytes):
        if len(source) > MAX_PDF_BYTES:
            raise ValueError(f"PDF exceeds maximum size of {MAX_PDF_BYTES // (1024 * 1024)} MB.")
        reader = PdfReader(BytesIO(source))
    else:
        reader = PdfReader(source)

    pages: list[str] = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception as exc:
            logger.warning("Failed to extract page text: %s", exc)
            page_text = ""
        if page_text.strip():
            pages.append(page_text)

    if not pages:
        raise ValueError("No readable text could be extracted from the PDF.")

    combined = _normalize_whitespace("\n\n".join(pages))
    if len(combined) < 50:
        raise ValueError("Extracted PDF text is too short for meaningful analysis.")

    return combined


def save_pdf_upload(upload_dir: Path, filename: str, data: bytes) -> Path:
    """Persist an uploaded PDF under upload_dir and return its path."""
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w.\-]", "_", filename) or "document.pdf"
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"
    dest = upload_dir / safe_name
    dest.write_bytes(data)
    return dest
