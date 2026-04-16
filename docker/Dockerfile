## syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder
WORKDIR /app
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Build wheels with a cached pip dir for faster rebuilds.
COPY requirements/base.txt ./requirements/base.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir=/wheels -r ./requirements/base.txt

FROM python:3.12-slim AS runner
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements/base.txt ./requirements/base.txt
COPY --from=builder /wheels /wheels
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-index --find-links=/wheels -r ./requirements/base.txt \
    && rm -rf /wheels

RUN useradd -m app
COPY --chown=app:app . .
USER app

FROM runner AS prod_runner
# reserved for future prod hardening
