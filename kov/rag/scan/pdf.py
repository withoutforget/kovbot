from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import DependencyError


@dataclass(frozen=True)
class PdfTextExtraction:
    page_texts: list[str]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_text_per_page(pdf_bytes: bytes, max_pages: int | None = None) -> PdfTextExtraction:
    try:
        # Some PDFs in the wild have broken xref tables; strict=False improves resilience.
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
    except DependencyError as e:
        # pypdf requires cryptography for AES-encrypted PDFs.
        raise ValueError("Encrypted PDF requires cryptography dependency") from e

    if getattr(reader, "is_encrypted", False):
        try:
            ok = reader.decrypt("")  # may succeed for PDFs without a user password
        except Exception as e:  # pragma: no cover
            raise ValueError("Encrypted PDF is not supported") from e
        if not ok:
            raise ValueError("Encrypted PDF is not supported (password required)")

    page_texts: list[str] = []
    for i, page in enumerate(reader.pages):
        if max_pages is not None and i >= max_pages:
            break
        text = page.extract_text() or ""
        page_texts.append(text)
    return PdfTextExtraction(page_texts=page_texts)


def detect_pdf_type(page_texts: list[str]) -> str:
    if not page_texts:
        return "unknown"
    nonempty = sum(1 for t in page_texts if t.strip())
    ratio = nonempty / max(len(page_texts), 1)
    if ratio > 0.9:
        return "text"
    if ratio < 0.1:
        return "scanned"
    return "mixed"
