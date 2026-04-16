FROM python:3.12-slim AS runner

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      postgresql-client \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ ./requirements/
RUN pip install --no-cache-dir -r requirements/base.txt

COPY . .

RUN useradd -m app && chown -R app:app /app
USER app

ENTRYPOINT ["python", "-m", "kov.backup.runner"]

