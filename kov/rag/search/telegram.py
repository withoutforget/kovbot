from __future__ import annotations

from kov.rag.types import TelegramMessagePart


def split_telegram(text: str, safe_limit_chars: int, max_parts: int) -> list[TelegramMessagePart]:
    t = (text or "").strip()
    if len(t) <= safe_limit_chars:
        return [TelegramMessagePart(part=1, total_parts=1, text=t)]
    parts: list[str] = []
    paragraphs = [p for p in t.split("\n\n") if p.strip()]
    buf = ""
    for p in paragraphs:
        candidate = (buf + ("\n\n" if buf else "") + p).strip()
        if len(candidate) <= safe_limit_chars:
            buf = candidate
            continue
        if buf:
            parts.append(buf)
            buf = ""
        if len(p) <= safe_limit_chars:
            buf = p
        else:
            # hard split
            for i in range(0, len(p), safe_limit_chars):
                parts.append(p[i : i + safe_limit_chars])
            buf = ""
        if len(parts) >= max_parts:
            break
    if buf and len(parts) < max_parts:
        parts.append(buf)
    parts = parts[:max_parts]
    total = len(parts)
    return [TelegramMessagePart(part=i + 1, total_parts=total, text=parts[i]) for i in range(total)]

