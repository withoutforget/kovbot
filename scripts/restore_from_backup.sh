#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

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
docker compose run --rm \
  -e PYTHONUNBUFFERED=1 \
  backup-restore "$ARCHIVE"
