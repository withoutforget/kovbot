from __future__ import annotations

import uuid

from kov.config import AppConfig
from kov.rag.search.normalize import basic_keywords, normalize_query
from kov.rag.types import SearchPlan, SearchQueryPlanItem


def plan_queries(*, config: AppConfig, user_query: str, language: str, search_profile: str) -> SearchPlan:
    request_id = str(uuid.uuid4())
    normalized = normalize_query(user_query)
    kws = basic_keywords(user_query, limit=10)

    queries: list[SearchQueryPlanItem] = []
    base = " ".join(kws) if kws else user_query
    intents = [
        ("quick_advice", "technique"),
        ("psychoeducation", "theory"),
        ("exercise_first", "exercise"),
        ("crisis_sensitive", "crisis"),
    ]
    max_q = config.rag_search.planner.max_queries
    for i, (profile_key, intent) in enumerate(intents, start=1):
        if len(queries) >= max_q:
            break
        if search_profile and search_profile != profile_key and search_profile != "quick_advice":
            continue
        queries.append(
            SearchQueryPlanItem(
                query_id=f"q{i}",
                text=f"{base} {intent}".strip(),
                intent_type=intent,
                weight=1.0,
                topic_tags=normalized.symptoms,
                preferred_content_types=["exercise", "checklist", "text"],
            )
        )

    if not queries:
        queries.append(SearchQueryPlanItem(query_id="q1", text=base, intent_type="mixed", weight=1.0))

    return SearchPlan(
        request_id=request_id,
        user_query=user_query,
        language=language,
        search_profile=search_profile or "quick_advice",
        normalized_state=normalized,
        global_filters={"language": [language]},
        queries=queries[:max_q],
    )

