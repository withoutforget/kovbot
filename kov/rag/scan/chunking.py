from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Chunk:
    text: str
    page_start: int
    page_end: int
    content_type: str = "text"
    heading_path: list[str] | None = None


_SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")
_SPACES_RE = re.compile(r"[ \t]+")
_PAGE_NUM_RE = re.compile(r"^\s*(стр\.?|страница)?\s*\d+\s*$", re.IGNORECASE)
_ONLY_PUNCT_RE = re.compile(r"^[\W_]+$", re.UNICODE)


def simple_chunk_text(
    *,
    page_texts: list[str],
    max_chars: int,
    overlap_chars: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    buf = ""
    buf_page_start = 1
    current_page = 1

    def flush(page_end: int) -> None:
        nonlocal buf, buf_page_start
        text = buf.strip()
        if not text:
            buf = ""
            return
        chunks.append(Chunk(text=text, page_start=buf_page_start, page_end=page_end, heading_path=[]))
        if overlap_chars > 0 and len(text) > overlap_chars:
            buf = text[-overlap_chars:]
            buf_page_start = page_end
        else:
            buf = ""

    for text in page_texts:
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
        for p in paragraphs:
            if not buf:
                buf_page_start = current_page
            if len(p) > max_chars:
                # flush existing buffer and hard-split long paragraph
                if buf:
                    flush(current_page)
                for i in range(0, len(p), max_chars):
                    part = p[i : i + max_chars]
                    if part.strip():
                        chunks.append(
                            Chunk(
                                text=part.strip(),
                                page_start=current_page,
                                page_end=current_page,
                                heading_path=[],
                            )
                        )
                buf = ""
                continue
            if len(buf) + len(p) + 1 > max_chars:
                flush(current_page)
            buf = (buf + "\n" + p).strip()
        current_page += 1
    flush(current_page - 1 if current_page > 1 else 1)
    return chunks


def _normalize_line(line: str) -> str:
    line = line.replace("\u00a0", " ").strip()
    line = _SPACES_RE.sub(" ", line)
    return line


def _extract_page_paragraphs(page_text: str) -> list[str]:
    """
    Convert raw page text into paragraph-like units:
    - blank lines separate paragraphs
    - within a paragraph, join lines with spaces
    - fix hyphenation at line breaks ("сло-\nво" -> "слово")
    """
    if not page_text:
        return []
    lines = page_text.splitlines()
    paragraphs: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        # join with newline marker to handle hyphenated breaks
        joined = "\n".join(buf).strip()
        # de-hyphenate across line breaks
        joined = re.sub(r"([A-Za-zА-Яа-яЁё])-\n([A-Za-zА-Яа-яЁё])", r"\1\2", joined)
        # join remaining single newlines into spaces
        joined = joined.replace("\n", " ")
        joined = _SPACES_RE.sub(" ", joined).strip()
        if joined:
            paragraphs.append(joined)
        buf = []

    for raw in lines:
        line = raw.rstrip("\r")
        if not line.strip():
            flush()
            continue
        buf.append(_normalize_line(line))
    flush()
    return paragraphs


def _strip_repeated_headers_footers(page_paragraphs: list[list[str]]) -> list[list[str]]:
    """
    Best-effort removal of repeated headers/footers:
    - take first 1 and last 1 paragraph per page as candidates
    - remove those that repeat across many pages and look short
    """
    pages = [p for p in page_paragraphs if p]
    if len(pages) < 5:
        return page_paragraphs

    first_counts: dict[str, int] = {}
    last_counts: dict[str, int] = {}
    for paras in pages:
        first = paras[0]
        last = paras[-1]
        first_counts[first] = first_counts.get(first, 0) + 1
        last_counts[last] = last_counts.get(last, 0) + 1

    threshold = max(2, int(len(pages) * 0.3))
    repeated_first = {t for t, c in first_counts.items() if c >= threshold and len(t) <= 120}
    repeated_last = {t for t, c in last_counts.items() if c >= threshold and len(t) <= 120}

    stripped: list[list[str]] = []
    for paras in page_paragraphs:
        if not paras:
            stripped.append(paras)
            continue
        out = list(paras)
        if out and out[0] in repeated_first:
            out = out[1:]
        if out and out[-1] in repeated_last:
            out = out[:-1]
        stripped.append(out)
    return stripped


def _is_low_signal(text: str, *, min_alpha_chars: int) -> bool:
    t = text.strip()
    if not t:
        return True
    if _ONLY_PUNCT_RE.match(t):
        return True
    if _PAGE_NUM_RE.match(t):
        return True
    alpha = sum(1 for ch in t if ch.isalpha())
    return alpha < min_alpha_chars


def _split_long_paragraph_to_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_SPLIT_RE.split(text.strip()) if p.strip()]
    return parts or [text.strip()]


def semantic_chunk_text(
    *,
    page_texts: list[str],
    max_chars: int,
    overlap_chars: int,
    strip_repeated_headers_footers: bool = True,
    drop_low_signal_paragraphs: bool = True,
    min_alpha_chars: int = 20,
) -> list[Chunk]:
    """
    A more semantic chunker than `simple_chunk_text`:
    - builds paragraph units per page
    - optionally removes repeated headers/footers and low-signal paragraphs (page numbers, punctuation-only, etc.)
    - packs paragraphs into chunks up to `max_chars` without cutting in the middle when possible
    - if a single paragraph is too long, it is split by sentence boundaries as a fallback
    """
    per_page = [_extract_page_paragraphs(t) for t in page_texts]
    if strip_repeated_headers_footers:
        per_page = _strip_repeated_headers_footers(per_page)

    chunks: list[Chunk] = []
    buf_parts: list[str] = []
    buf_page_start = 1
    buf_page_end = 1

    def current_len() -> int:
        if not buf_parts:
            return 0
        # join with double newlines to keep paragraph boundaries in stored text
        return len("\n\n".join(buf_parts))

    def flush() -> None:
        nonlocal buf_parts, buf_page_start, buf_page_end
        text = "\n\n".join(buf_parts).strip()
        if not text:
            buf_parts = []
            return
        chunks.append(Chunk(text=text, page_start=buf_page_start, page_end=buf_page_end, heading_path=[]))
        if overlap_chars > 0 and len(text) > overlap_chars:
            tail = text[-overlap_chars:].strip()
            buf_parts = [tail] if tail else []
            buf_page_start = buf_page_end
        else:
            buf_parts = []

    for page_idx, paras in enumerate(per_page, start=1):
        for para in paras:
            if drop_low_signal_paragraphs and _is_low_signal(para, min_alpha_chars=min_alpha_chars):
                continue

            # split too-long paragraph by sentences first
            units = [para]
            if len(para) > max_chars:
                units = _split_long_paragraph_to_sentences(para)

            for unit in units:
                if drop_low_signal_paragraphs and _is_low_signal(unit, min_alpha_chars=min_alpha_chars):
                    continue
                if not buf_parts:
                    buf_page_start = page_idx
                    buf_page_end = page_idx

                prospective = ("\n\n".join(buf_parts + [unit])).strip() if buf_parts else unit
                if len(prospective) <= max_chars:
                    buf_parts.append(unit)
                    buf_page_end = page_idx
                    continue

                # buffer would overflow
                flush()
                if len(unit) <= max_chars:
                    buf_parts = [unit]
                    buf_page_start = page_idx
                    buf_page_end = page_idx
                else:
                    # hard-split as a last resort
                    for i in range(0, len(unit), max_chars):
                        part = unit[i : i + max_chars].strip()
                        if not part:
                            continue
                        chunks.append(
                            Chunk(text=part, page_start=page_idx, page_end=page_idx, heading_path=[])
                        )
                    buf_parts = []

    flush()
    return chunks
