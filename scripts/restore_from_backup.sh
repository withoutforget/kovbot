#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

compose_files=(-f docker-compose.yml)
if [[ -f docker-compose.prod.yml ]]; then
  # Restore should happen in the same compose topology as the running stack.
  if [[ -n "${ADMIN_PASSWORD:-}" ]] || [[ "${KOV_CONFIG_PATH:-}" == *"configs/prod.yaml"* ]]; then
    compose_files+=(-f docker-compose.prod.yml)
  fi
fi

ARCHIVE="${1:-}"
if [[ -z "$ARCHIVE" ]]; then
  read -r -p "Введите путь к backup_*.tar.gz: " ARCHIVE
fi

if [[ -z "$ARCHIVE" ]]; then
  echo "Archive path is required"
  exit 1
fi

if [[ "$ARCHIVE" != /* ]]; then
  ARCHIVE="/backups/$ARCHIVE"
fi

echo "Restoring from (container path): $ARCHIVE"
docker compose "${compose_files[@]}" run --rm \
  -e PYTHONUNBUFFERED=1 \
  backup-restore "$ARCHIVE"
