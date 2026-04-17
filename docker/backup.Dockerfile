FROM python:3.12-slim AS runner

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

ARG PG_MAJOR=16
ENV PG_MAJOR=${PG_MAJOR}
ENV PATH="/usr/lib/postgresql/${PG_MAJOR}/bin:${PATH}"

# We need `pg_dump/pg_restore` that match the Postgres major version (server is `postgres:${PG_MAJOR}`).
# `python:*-slim` (Debian) doesn't ship `postgresql-client-${PG_MAJOR}` by default, so we add PGDG.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      gnupg \
    && install -d /usr/share/keyrings \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
      "postgresql-client-${PG_MAJOR}" \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ ./requirements/
RUN pip install --no-cache-dir -r requirements/base.txt

COPY . .

RUN useradd -m app && chown -R app:app /app
USER app

ENTRYPOINT ["python", "-m", "kov.backup.runner"]
