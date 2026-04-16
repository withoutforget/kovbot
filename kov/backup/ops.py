from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import httpx


_TS_RE = re.compile(r"^backup_(\\d{8}T\\d{6}Z)\\.tar\\.gz$")


@dataclass(frozen=True)
class BackupPaths:
    archive_path: Path
    tmp_dir: Path


def utc_now_compact() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _require_env(name: str) -> str:
    val = os.environ.get(name, "")
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


def _postgres_conn_uri() -> str:
    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "kov")
    user = os.environ.get("POSTGRES_USER", "kov")
    password = os.environ.get("POSTGRES_PASSWORD", "kov")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, check=True, env=env or os.environ.copy())


def create_backup_archive(
    *,
    backups_dir: Path,
    qdrant_url: str,
    qdrant_collection: str,
    include_s3_bucket: bool,
) -> BackupPaths:
    backups_dir.mkdir(parents=True, exist_ok=True)
    ts = utc_now_compact()
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"kov_backup_{ts}_"))
    archive_path = backups_dir / f"backup_{ts}.tar.gz"

    try:
        # 1) Postgres logical dump (custom format).
        pg_uri = _postgres_conn_uri()
        pg_dump_path = tmp_dir / "postgres.dump"
        _run(
            [
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--file",
                str(pg_dump_path),
                pg_uri,
            ],
            env={**os.environ, "PGCONNECT_TIMEOUT": "10"},
        )

        # 2) Qdrant snapshot.
        snapshot_name = _qdrant_create_snapshot(qdrant_url=qdrant_url, collection=qdrant_collection)
        qdrant_snapshot_path = tmp_dir / f"qdrant_{qdrant_collection}_{snapshot_name}"
        _qdrant_download_snapshot(
            qdrant_url=qdrant_url,
            collection=qdrant_collection,
            snapshot_name=snapshot_name,
            out_path=qdrant_snapshot_path,
        )

        # 3) Optional: bucket contents (download -> tar).
        if include_s3_bucket:
            s3_dump = tmp_dir / "s3_bucket"
            _s3_download_bucket(out_dir=s3_dump)

        # Pack archive.
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(pg_dump_path, arcname="postgres.dump")
            tf.add(qdrant_snapshot_path, arcname=qdrant_snapshot_path.name)
            if include_s3_bucket:
                tf.add(tmp_dir / "s3_bucket", arcname="s3_bucket")

        return BackupPaths(archive_path=archive_path, tmp_dir=tmp_dir)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def cleanup_backup_tmp(tmp_dir: Path) -> None:
    shutil.rmtree(tmp_dir, ignore_errors=True)


def upload_to_s3(*, archive_path: Path) -> str:
    bucket = _require_env("BACKUP_S3_BUCKET")
    prefix = os.environ.get("BACKUP_S3_PREFIX", "backups").strip("/") or "backups"
    endpoint_url = os.environ.get("BACKUP_S3_ENDPOINT_URL") or None
    region = os.environ.get("BACKUP_S3_REGION") or os.environ.get("S3_REGION") or "us-east-1"
    access_key = _require_env("BACKUP_S3_ACCESS_KEY")
    secret_key = _require_env("BACKUP_S3_SECRET_KEY")

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )
    key = f"{prefix}/{archive_path.name}"
    s3.upload_file(str(archive_path), bucket, key)
    return f"s3://{bucket}/{key}"


def rotate_local(*, backups_dir: Path, keep_hours: int) -> int:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=keep_hours)
    deleted = 0
    for p in backups_dir.glob("backup_*.tar.gz"):
        m = _TS_RE.match(p.name)
        if not m:
            continue
        ts = datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        if ts < cutoff:
            p.unlink(missing_ok=True)
            deleted += 1
    return deleted


def rotate_s3(*, keep_hours: int) -> int:
    bucket = os.environ.get("BACKUP_S3_BUCKET", "")
    if not bucket:
        return 0
    prefix = os.environ.get("BACKUP_S3_PREFIX", "backups").strip("/") or "backups"
    endpoint_url = os.environ.get("BACKUP_S3_ENDPOINT_URL") or None
    region = os.environ.get("BACKUP_S3_REGION") or os.environ.get("S3_REGION") or "us-east-1"
    access_key = _require_env("BACKUP_S3_ACCESS_KEY")
    secret_key = _require_env("BACKUP_S3_SECRET_KEY")

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=keep_hours)
    deleted = 0
    token: str | None = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": f"{prefix}/", "MaxKeys": 1000}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            key = obj.get("Key") or ""
            name = key.rsplit("/", 1)[-1]
            m = _TS_RE.match(name)
            if not m:
                continue
            ts = datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            if ts < cutoff:
                s3.delete_object(Bucket=bucket, Key=key)
                deleted += 1
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return deleted


def restore_from_archive(*, archive_path: Path, qdrant_url: str, qdrant_collection: str) -> None:
    tmp_dir = Path(tempfile.mkdtemp(prefix="kov_restore_"))
    try:
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(tmp_dir)

        # 1) Postgres restore.
        pg_uri = _postgres_conn_uri()
        dump_path = tmp_dir / "postgres.dump"
        if dump_path.exists():
            _run(
                [
                    "pg_restore",
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--no-acl",
                    "--dbname",
                    pg_uri,
                    str(dump_path),
                ],
                env={**os.environ, "PGCONNECT_TIMEOUT": "10"},
            )

        # 2) Qdrant restore (upload snapshot).
        snap = next(tmp_dir.glob(f"qdrant_{qdrant_collection}_*"), None)
        if snap:
            _qdrant_upload_snapshot(
                qdrant_url=qdrant_url,
                collection=qdrant_collection,
                snapshot_path=snap,
            )

        # 3) Optional: restore bucket contents.
        s3_dir = tmp_dir / "s3_bucket"
        if s3_dir.exists():
            _s3_upload_bucket(in_dir=s3_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _qdrant_create_snapshot(*, qdrant_url: str, collection: str) -> str:
    base = qdrant_url.rstrip("/")
    url = f"{base}/collections/{collection}/snapshots"
    with httpx.Client(timeout=60) as client:
        resp = client.post(url)
        resp.raise_for_status()
        data = resp.json()
    name = (data.get("result") or {}).get("name") or data.get("result") or ""
    if not name:
        # fallback: list and take latest
        with httpx.Client(timeout=60) as client:
            resp2 = client.get(url)
            resp2.raise_for_status()
            items = (resp2.json().get("result") or []) if isinstance(resp2.json(), dict) else []
        if items:
            name = items[-1].get("name") or ""
    if not name:
        raise RuntimeError("Failed to create qdrant snapshot")
    return str(name)


def _qdrant_download_snapshot(
    *, qdrant_url: str, collection: str, snapshot_name: str, out_path: Path
) -> None:
    base = qdrant_url.rstrip("/")
    url = f"{base}/collections/{collection}/snapshots/{snapshot_name}"
    with httpx.Client(timeout=None) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with out_path.open("wb") as f:
                for chunk in resp.iter_bytes():
                    f.write(chunk)


def _qdrant_upload_snapshot(*, qdrant_url: str, collection: str, snapshot_path: Path) -> None:
    base = qdrant_url.rstrip("/")
    url = f"{base}/collections/{collection}/snapshots/upload"
    with httpx.Client(timeout=None) as client:
        files = {"snapshot": (snapshot_path.name, snapshot_path.read_bytes(), "application/octet-stream")}
        resp = client.post(url, files=files)
        resp.raise_for_status()


def _s3_client_from_app_env():
    endpoint_url = os.environ.get("S3_ENDPOINT_URL") or None
    region = os.environ.get("S3_REGION") or "us-east-1"
    access_key = _require_env("S3_ACCESS_KEY")
    secret_key = _require_env("S3_SECRET_KEY")
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def _s3_download_bucket(*, out_dir: Path) -> None:
    bucket = _require_env("S3_BUCKET")
    out_dir.mkdir(parents=True, exist_ok=True)
    s3 = _s3_client_from_app_env()
    backup_bucket = os.environ.get("BACKUP_S3_BUCKET", "")
    backup_prefix = (os.environ.get("BACKUP_S3_PREFIX", "backups").strip("/") or "backups") + "/"
    token: str | None = None
    while True:
        kwargs = {"Bucket": bucket, "MaxKeys": 1000}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            key = obj.get("Key")
            if not key:
                continue
            if backup_bucket and backup_bucket == bucket and key.startswith(backup_prefix):
                continue
            target = out_dir / key
            target.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, key, str(target))
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")


def _s3_upload_bucket(*, in_dir: Path) -> None:
    bucket = _require_env("S3_BUCKET")
    s3 = _s3_client_from_app_env()
    for path in in_dir.rglob("*"):
        if not path.is_file():
            continue
        key = str(path.relative_to(in_dir)).replace("\\", "/")
        s3.upload_file(str(path), bucket, key)
