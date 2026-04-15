from __future__ import annotations

import boto3
from botocore.client import Config


def create_s3_client(endpoint_url: str, access_key: str, secret_key: str, region: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket(s3, bucket: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
        return
    except Exception:
        pass
    s3.create_bucket(Bucket=bucket)

