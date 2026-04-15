from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    text: str
    page_start: int
    page_end: int
    content_type: str = "text"
    heading_path: list[str] | None = None


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
