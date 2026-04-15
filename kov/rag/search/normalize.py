from __future__ import annotations

import re

from kov.rag.types import NormalizedState


CRISIS_KEYWORDS = [
    "суицид",
    "самоубий",
    "умереть",
    "не хочу жить",
    "навредить себе",
    "порез",
]


def normalize_query(text: str) -> NormalizedState:
    t = (text or "").strip()
    lower = t.lower()
    crisis = [k for k in CRISIS_KEYWORDS if k in lower]
    symptoms = []
    for kw in ["тревог", "депресс", "паник", "окр", "стресс", "травм", "бессон"]:
        if kw in lower:
            symptoms.append(kw)
    urgency = "high" if crisis else "normal"
    summary = t[:200]
    return NormalizedState(summary=summary, symptoms=symptoms, urgency=urgency, crisis_signals=crisis)


def basic_keywords(text: str, limit: int = 8) -> list[str]:
    tokens = re.findall(r"[\w\-]{3,}", (text or "").lower())
    stop = {"когда", "почему", "чтобы", "потому", "очень", "просто", "сейчас", "теперь"}
    uniq: list[str] = []
    for tok in tokens:
        if tok in stop:
            continue
        if tok not in uniq:
            uniq.append(tok)
        if len(uniq) >= limit:
            break
    return uniq
