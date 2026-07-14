"""
Backblaze B2 upload utility using boto3's S3-compatible API.

B2-specific requirements:
- Use a real region string, for example "us-west-004". Do not use "auto".
- Set signature_version="s3v4" explicitly.
- Set endpoint_url to the B2 S3-compatible endpoint.
"""

from __future__ import annotations

import os
from pathlib import Path

import boto3
from botocore.config import Config


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _required_env() -> dict[str, str]:
    """
    Resolve required B2 settings.

    Media storage already uses B2_KEY_ID/B2_APPLICATION_KEY in this repo. The
    backup prompt used B2_ACCESS_KEY_ID/B2_SECRET_ACCESS_KEY. Support both, with
    the existing repo names taking precedence, so backups work with the current
    VPS configuration without duplicating secrets.
    """
    values = {
        "key_id": _first_env("B2_KEY_ID", "B2_ACCESS_KEY_ID"),
        "application_key": _first_env("B2_APPLICATION_KEY", "B2_SECRET_ACCESS_KEY"),
        "bucket": os.environ.get("B2_BUCKET_NAME"),
        "endpoint_url": os.environ.get("B2_ENDPOINT_URL"),
        "region": os.environ.get("B2_REGION"),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            f"Missing B2 env vars for backup upload: {', '.join(missing)}. "
            "Set B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME, B2_ENDPOINT_URL, and B2_REGION "
            "before enabling B2 backups."
        )
    if values["region"].lower() == "auto":
        raise RuntimeError("B2_REGION must be a real Backblaze region string, not 'auto'.")
    return values  # type: ignore[return-value]


def get_b2_client():
    """Return a boto3 S3 client configured for Backblaze B2."""
    env = _required_env()
    return boto3.client(
        "s3",
        endpoint_url=env["endpoint_url"],
        aws_access_key_id=env["key_id"],
        aws_secret_access_key=env["application_key"],
        region_name=env["region"],
        config=Config(signature_version="s3v4"),
    )


def upload_backup_to_b2(local_path: str) -> str:
    """
    Upload a local backup file to the B2 bucket and return the object key.

    The object key preserves the filename under the backups/ prefix. The caller
    decides whether upload failure is fatal; the backup task keeps local backups
    even if this offsite upload fails.
    """
    path = Path(local_path)
    if not path.is_file():
        raise FileNotFoundError(f"Backup file does not exist: {local_path}")

    env = _required_env()
    object_key = f"backups/{path.name}"
    get_b2_client().upload_file(
        Filename=str(path),
        Bucket=env["bucket"],
        Key=object_key,
        ExtraArgs={"StorageClass": "STANDARD"},
    )
    return object_key


def verify_b2_connection() -> dict:
    """Return a small status dict proving bucket access works."""
    try:
        env = _required_env()
        get_b2_client().list_objects_v2(Bucket=env["bucket"], MaxKeys=1)
        return {"b2": True, "bucket": env["bucket"]}
    except Exception as exc:
        return {"b2": False, "error": str(exc)}
