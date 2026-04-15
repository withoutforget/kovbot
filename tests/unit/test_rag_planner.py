from kov.config import AppConfig
from kov.rag.search.planner import plan_queries


def test_plan_queries_respects_max_queries():
    cfg = AppConfig.model_validate(
        {
            "env": "test",
            "logging": {"level": "INFO"},
            "postgres": {"dsn": "postgresql+asyncpg://u:p@localhost:5432/db"},
            "qdrant": {"url": "http://localhost:6333", "collection": "c", "vector_size": 8},
            "s3": {
                "endpoint_url": "http://localhost:9000",
                "access_key": "a",
                "secret_key": "b",
                "bucket": "x",
                "region": "us-east-1",
            },
            "rag_search": {"planner": {"max_queries": 2}},
            "rag_scan": {"chunking": {"max_chars": 10, "overlap_chars": 0}},
            "llm": {},
            "telegram": {},
        }
    )
    plan = plan_queries(config=cfg, user_query="мне тревожно и плохо сплю", language="ru", search_profile="quick_advice")
    assert len(plan.queries) <= 2

