from __future__ import annotations

import json
import uuid

from kov.config import AppConfig
from kov.llm.openai_compat import OpenAICompatClient
from kov.logging import get_logger
from kov.rag.search.normalize import basic_keywords, normalize_query
from kov.rag.types import SearchPlan, SearchQueryPlanItem


def _plan_queries_heuristic(*, config: AppConfig, user_query: str, language: str, search_profile: str) -> SearchPlan:
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


async def plan_queries(*, config: AppConfig, user_query: str, language: str, search_profile: str) -> SearchPlan:
    """
    Prefer an LLM-based query planner (returns JSON with query variants) and fall back to
    the heuristic planner on any error or if LLM is not configured.
    """
    log = get_logger(component="rag_planner")
    planner_cfg = config.rag_search.planner

    if not planner_cfg.use_llm:
        return _plan_queries_heuristic(
            config=config, user_query=user_query, language=language, search_profile=search_profile
        )

    if not (config.llm.base_url and config.llm.api_key and config.llm.model):
        return _plan_queries_heuristic(
            config=config, user_query=user_query, language=language, search_profile=search_profile
        )

    max_q = max(1, int(planner_cfg.max_queries or 20))
    model = (planner_cfg.model or "").strip() or config.llm.model
    max_tokens = max(200, int(planner_cfg.max_tokens or 800))

    system = (
        "Ты — query planner для RAG. Сгенерируй релевантные поисковые запросы (варианты) к векторной базе.\n"
        "Требования:\n"
        f"- Язык запросов: {language or 'ru'}\n"
        f"- Профиль: {search_profile or 'quick_advice'} (подстрой тон/акценты под профиль)\n"
        f"- Количество: 1..{max_q}\n"
        "- Не добавляй мусорные служебные слова.\n"
        "- Не добавляй английские суффиксы типа 'crisis/exercise/theory/technique' — пиши как человек.\n"
        "- Выведи строго JSON-объект вида:\n"
        "  {\"queries\": [{\"text\": \"...\", \"intent_type\": \"mixed|technique|theory|exercise|crisis\", \"weight\": 0.0..2.0}]}\n"
        "Никакого текста вне JSON."
    )
    user = json.dumps({"user_query": user_query}, ensure_ascii=False)

    client = OpenAICompatClient(config.llm)
    try:
        raw = await client.chat_completions(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            model=model,
            temperature=0.2,
            max_tokens=max_tokens,
        )
        txt = OpenAICompatClient.extract_text(raw).strip()
        data = json.loads(txt) if txt else {}
        items = data.get("queries") if isinstance(data, dict) else None
        if not isinstance(items, list) or not items:
            raise ValueError("planner returned empty queries")

        normalized = normalize_query(user_query)
        out: list[SearchQueryPlanItem] = []
        seen: set[str] = set()
        for idx, it in enumerate(items, start=1):
            if len(out) >= max_q:
                break
            if not isinstance(it, dict):
                continue
            text = str(it.get("text") or "").strip()
            if not text or len(text) < 4:
                continue
            key = " ".join(text.lower().split())
            if key in seen:
                continue
            seen.add(key)
            intent = str(it.get("intent_type") or "mixed").strip() or "mixed"
            weight_raw = it.get("weight", 1.0)
            try:
                weight = float(weight_raw)
            except Exception:
                weight = 1.0
            weight = max(0.1, min(2.0, weight))
            out.append(
                SearchQueryPlanItem(
                    query_id=f"q{idx}",
                    text=text,
                    intent_type=intent,
                    weight=weight,
                    topic_tags=normalized.symptoms,
                    preferred_content_types=["exercise", "checklist", "text"],
                )
            )

        if not out:
            raise ValueError("planner returned no valid items")

        plan = SearchPlan(
            request_id=str(uuid.uuid4()),
            user_query=user_query,
            language=language,
            search_profile=search_profile or "quick_advice",
            normalized_state=normalized,
            global_filters={"language": [language]},
            queries=out[:max_q],
        )
        log.info("planner_llm_ok", queries=len(plan.queries), model=model)
        return plan
    except Exception as e:
        log.warning("planner_llm_failed_fallback", error=str(e), model=model)
        return _plan_queries_heuristic(
            config=config, user_query=user_query, language=language, search_profile=search_profile
        )
