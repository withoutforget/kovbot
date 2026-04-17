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

# If the path exists on the host, mount it and restore from there.
HOST_ARCHIVE=""
if [[ -f "$ARCHIVE" ]]; then
  HOST_ARCHIVE="$(realpath "$ARCHIVE")"
elif [[ "$ARCHIVE" == /* ]] && [[ -f "$ARCHIVE" ]]; then
  HOST_ARCHIVE="$ARCHIVE"
fi

MOUNTS=()
if [[ -n "$HOST_ARCHIVE" ]]; then
  HOST_DIR="$(dirname "$HOST_ARCHIVE")"
  HOST_FILE="$(basename "$HOST_ARCHIVE")"
  ARCHIVE="/in/$HOST_FILE"
  MOUNTS+=(-v "${HOST_DIR}:/in:ro")
elif [[ "$ARCHIVE" != /* ]]; then
  # Fallback: resolve inside the backups volume.
  ARCHIVE="/backups/$ARCHIVE"
fi

echo "Restoring from (container path): $ARCHIVE"
docker compose "${compose_files[@]}" run --rm \
  -e PYTHONUNBUFFERED=1 \
  "${MOUNTS[@]}" \
  backup-restore "$ARCHIVE"
