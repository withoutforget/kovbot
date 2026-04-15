from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from pypdf import PdfReader


@dataclass(frozen=True)
class PdfTextExtraction:
    page_texts: list[str]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_text_per_page(pdf_bytes: bytes, max_pages: int | None = None) -> PdfTextExtraction:
    reader = PdfReader(io.BytesIO(pdf_bytes))
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
