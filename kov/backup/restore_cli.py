from __future__ import annotations

import argparse
import os
from pathlib import Path

from kov.backup.ops import restore_from_archive
from kov.config import load_config
from kov.logging import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore Kov from a backup archive.")
    parser.add_argument("archive", help="Path to backup_*.tar.gz")
    args = parser.parse_args()

    config = load_config()
    configure_logging(config.logging.level)

    archive_path = Path(args.archive).expanduser().resolve()
    if not archive_path.exists():
        raise SystemExit(f"Archive not found: {archive_path}")

    restore_from_archive(
        archive_path=archive_path,
        qdrant_url=config.qdrant.url,
        qdrant_collection=config.qdrant.collection,
    )


if __name__ == "__main__":
    # Keep restore CLI sync for simple container usage.
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()

