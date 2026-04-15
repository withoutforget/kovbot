from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
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


class RagSearchConfig(BaseModel):
    pipeline_version: str = "1.0"
    planner: RagSearchPlannerConfig = Field(default_factory=RagSearchPlannerConfig)
    retrieval: RagSearchRetrievalConfig = Field(default_factory=RagSearchRetrievalConfig)
    telegram: RagSearchTelegramConfig = Field(default_factory=RagSearchTelegramConfig)


class LlmConfig(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.2
    max_tokens: int = 800


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
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


@dataclass(frozen=True)
class ConfigPaths:
    path: Path


def load_config(path: str | None = None) -> AppConfig:
    config_path = Path(path or os.environ.get("KOV_CONFIG_PATH", "configs/dev.yaml"))
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw = _expand_env(raw)
    return AppConfig.model_validate(raw)

