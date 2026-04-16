FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements/ ./requirements/
RUN pip install --no-cache-dir -r requirements/base.txt

FROM python:3.12-slim AS runner
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
COPY --from=builder /usr/local /usr/local
COPY . .
RUN useradd -m app && chown -R app:app /app
USER app

FROM runner AS prod_runner
# reserved for future prod hardening
