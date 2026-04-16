from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:-|-)([^}]*))?\}")


def _expand_env_str(value: str) -> str:
    """
    Expand ${VAR}, $VAR and bash-like defaults: ${VAR:-default} / ${VAR-default}.

    os.path.expandvars() does not understand the default syntax, so we handle it first.
    """

    def repl(match: re.Match[str]) -> str:
        name, op, default = match.group(1), match.group(2), match.group(3)
        current = os.environ.get(name)
        if op is None:
            return current if current is not None else match.group(0)
        if op == ":-":
            return current if (current is not None and current != "") else (default or "")
        # op == "-"
        return current if current is not None else (default or "")

    expanded = _ENV_PATTERN.sub(repl, value)
    return os.path.expandvars(expanded)


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return _expand_env_str(value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


class LoggingConfig(BaseModel):
    level: str = "INFO"


class PostgresConfig(BaseModel):
    dsn: str


class QdrantConfig(BaseModel):
    url: str
    collection: str = "kov_chunks"
    vector_size: int = 64
    timeout_seconds: int = 120
    upsert_batch_size: int = 64


class S3Config(BaseModel):
    endpoint_url: str
    access_key: str
    secret_key: str
    bucket: str
    region: str = "us-east-1"


class RagScanChunkingConfig(BaseModel):
    max_chars: int = 1200
    overlap_chars: int = 120


class RagScanConfig(BaseModel):
    pipeline_version: str = "1.0"
    chunking: RagScanChunkingConfig = Field(default_factory=RagScanChunkingConfig)


class RagSearchPlannerConfig(BaseModel):
    max_queries: int = 20


class RagSearchRetrievalConfig(BaseModel):
    top_k_per_query: int = 10
    min_score: float = 0.0


class RagSearchTelegramConfig(BaseModel):
    safe_limit_chars: int = 3900
    max_parts: int = 3


class RagSearchExpanderConfig(BaseModel):
    seed_top_n: int = 10
    neighbor_window: int = 5  # chunks above/below seed
    max_context_chars: int = 24000  # total chars across all expanded contexts


class RagSearchConfig(BaseModel):
    pipeline_version: str = "1.0"
    planner: RagSearchPlannerConfig = Field(default_factory=RagSearchPlannerConfig)
    retrieval: RagSearchRetrievalConfig = Field(default_factory=RagSearchRetrievalConfig)
    expander: RagSearchExpanderConfig = Field(default_factory=RagSearchExpanderConfig)
    telegram: RagSearchTelegramConfig = Field(default_factory=RagSearchTelegramConfig)


class LlmConfig(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.2
    max_tokens: int = 800


class EmbeddingsConfig(BaseModel):
    provider: str = "fake"  # fake | openai_compat
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    batch_size: int = 64


class TelegramConfig(BaseModel):
    bot_token: str = ""
    api_base_url: str = "http://api:8000"


class AppConfig(BaseModel):
    env: str = "dev"
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    postgres: PostgresConfig
    qdrant: QdrantConfig
    s3: S3Config
    rag_scan: RagScanConfig = Field(default_factory=RagScanConfig)
    rag_search: RagSearchConfig = Field(default_factory=RagSearchConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


@dataclass(frozen=True)
class ConfigPaths:
    path: Path


def load_config(path: str | None = None) -> AppConfig:
    config_path = Path(path or os.environ.get("KOV_CONFIG_PATH", "configs/dev.yaml"))
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw = _expand_env(raw)
    return AppConfig.model_validate(raw)
