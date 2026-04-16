from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kov.backup.ops import (
    cleanup_backup_tmp,
    create_backup_archive,
    rotate_local,
    rotate_s3,
    upload_to_s3,
)
from kov.config import load_config
from kov.logging import configure_logging, get_logger


async def run_once() -> None:
    config = load_config()
    include_s3_bucket = os.environ.get("BACKUP_INCLUDE_S3_DATA", "1").strip() not in ("0", "false", "False")
    keep_hours = int(os.environ.get("BACKUP_KEEP_HOURS", "36"))
    backups_dir = Path(os.environ.get("BACKUP_LOCAL_DIR", "/backups"))

    paths = create_backup_archive(
        backups_dir=backups_dir,
        qdrant_url=config.qdrant.url,
        qdrant_collection=config.qdrant.collection,
        include_s3_bucket=include_s3_bucket,
    )
    cleanup_backup_tmp(paths.tmp_dir)

    uploaded_to = ""
    if os.environ.get("BACKUP_S3_BUCKET"):
        uploaded_to = upload_to_s3(archive_path=paths.archive_path)

    local_deleted = rotate_local(backups_dir=backups_dir, keep_hours=keep_hours)
    s3_deleted = rotate_s3(keep_hours=keep_hours)

    log = get_logger(component="backup")
    log.info(
        "backup_completed",
        archive=str(paths.archive_path),
        uploaded_to=uploaded_to,
        local_deleted=local_deleted,
        s3_deleted=s3_deleted,
    )


def _seconds_until_next_boundary(interval_minutes: int) -> int:
    now = datetime.now(tz=timezone.utc)
    epoch = int(now.timestamp())
    interval = interval_minutes * 60
    next_ts = ((epoch // interval) + 1) * interval
    return max(1, next_ts - epoch)


async def main() -> None:
    config = load_config()
    configure_logging(config.logging.level)
    log = get_logger(component="backup")
    interval_minutes = int(os.environ.get("BACKUP_INTERVAL_MINUTES", "120"))

    if os.environ.get("BACKUP_RUN_ONCE", "").strip() in ("1", "true", "True", "yes", "YES"):
        await run_once()
        return

    # First run immediately on start.
    while True:
        try:
            await run_once()
        except Exception as e:
            log.exception("backup_failed", error=str(e))

        sleep_s = _seconds_until_next_boundary(interval_minutes)
        log.info("backup_sleep", seconds=sleep_s)
        await asyncio.sleep(sleep_s)


if __name__ == "__main__":
    asyncio.run(main())
