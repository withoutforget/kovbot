from __future__ import annotations

import textwrap

from kov.config import load_config


def test_load_config_supports_bash_like_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("POSTGRES_USER", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)

    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        textwrap.dedent(
            """
            env: test
            logging:
              level: INFO

            postgres:
              dsn: postgresql+asyncpg://${POSTGRES_USER:-u}:${POSTGRES_PASSWORD:-p}@localhost:5432/kov

            qdrant:
              url: http://localhost:6333
              collection: kov_chunks
              vector_size: 64

            s3:
              endpoint_url: http://localhost:9000
              access_key: minioadmin
              secret_key: minioadmin
              bucket: kov-artifacts
              region: us-east-1
            """
        ).lstrip(),
        encoding="utf-8",
    )

    cfg = load_config(str(cfg_path))
    assert cfg.postgres.dsn == "postgresql+asyncpg://u:p@localhost:5432/kov"

