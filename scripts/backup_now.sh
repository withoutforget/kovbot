#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${ADMIN_PASSWORD:-}" ]]; then
  echo "ADMIN_PASSWORD is not set (needed for prod compose validation only)."
fi

echo "Running one-shot backup via docker compose..."
docker compose run --rm \
  -e BACKUP_INTERVAL_MINUTES=120 \
  -e BACKUP_KEEP_HOURS="${BACKUP_KEEP_HOURS:-36}" \
  -e BACKUP_INCLUDE_S3_DATA="${BACKUP_INCLUDE_S3_DATA:-1}" \
  backup-once

