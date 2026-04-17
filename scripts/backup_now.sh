#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

compose_files=(-f docker-compose.yml)
if [[ -f docker-compose.prod.yml ]]; then
  # In prod `ADMIN_PASSWORD` is always set (required by nginx in the prod overlay),
  # so we can safely auto-include the overlay to run the backup in the correct network.
  if [[ -n "${ADMIN_PASSWORD:-}" ]] || [[ "${KOV_CONFIG_PATH:-}" == *"configs/prod.yaml"* ]]; then
    compose_files+=(-f docker-compose.prod.yml)
  fi
fi

echo "Running one-shot backup via docker compose..."
docker compose "${compose_files[@]}" run --rm \
  -e BACKUP_RUN_ONCE=1 \
  -e BACKUP_INTERVAL_MINUTES=120 \
  -e BACKUP_KEEP_HOURS="${BACKUP_KEEP_HOURS:-36}" \
  -e BACKUP_INCLUDE_S3_DATA="${BACKUP_INCLUDE_S3_DATA:-0}" \
  backup-once

# Optional: export the newest archive from the `/backups` volume onto the host.
# Defaults to enabled because the common workflow is "create backup -> scp to prod".
if [[ "${BACKUP_EXPORT:-1}" != "0" ]]; then
  EXPORT_DIR="${BACKUP_EXPORT_DIR:-$PWD}"
  mkdir -p "$EXPORT_DIR"

  echo "Exporting latest backup archive to host dir: $EXPORT_DIR"
  docker compose "${compose_files[@]}" run --rm \
    --no-deps \
    -v "${EXPORT_DIR}:/out" \
    --entrypoint sh \
    backup-once -lc '
      set -eu
      latest="$(ls -1t /backups/backup_*.tar.gz 2>/dev/null | head -n 1 || true)"
      if [ -z "$latest" ]; then
        echo "No backup_*.tar.gz found in /backups" >&2
        exit 1
      fi
      base="$(basename "$latest")"
      out="/out/$base"
      if [ -e "$out" ]; then
        out="/out/${base%.tar.gz}_copy.tar.gz"
      fi
      cp "$latest" "$out"
      echo "Exported: $out"
    '
fi
