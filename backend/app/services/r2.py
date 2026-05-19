import logging
import os
import shutil
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from app.config import settings

logger = logging.getLogger(__name__)

LOCAL_STORAGE_ROOT = Path("/tmp/clipbandit-storage")


def _local_api_base_url() -> str:
    configured = (settings.backend_public_url or "").strip().rstrip("/")
    if configured:
        return configured
    return "http://localhost:8000"


class R2Client:
    def __init__(self):
        self._client = None
        self.use_local = False
        self.bucket_name = settings.r2_bucket_name
        LOCAL_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        self._init_client()

    def _is_placeholder(self, value: str | None) -> bool:
        if value is None:
            return True
        normalized = value.strip().lower()
        return normalized == "" or normalized == "placeholder" or "placeholder" in normalized

    def _credentials_ready(self) -> bool:
        required_values = (
            settings.r2_account_id,
            settings.r2_access_key_id,
            settings.r2_secret_access_key,
            settings.r2_bucket_name,
            settings.r2_endpoint_url,
        )
        return not any(self._is_placeholder(value) for value in required_values)

    def _init_client(self):
        if not self._credentials_ready():
            self.use_local = True
            logger.warning("R2 credentials are placeholders. Falling back to local storage at /tmp/clipbandit-storage.")
            return

        try:
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.r2_endpoint_url,
                aws_access_key_id=settings.r2_access_key_id,
                aws_secret_access_key=settings.r2_secret_access_key,
                region_name="auto",
            )
            self.use_local = False
        except Exception as exc:
            self.use_local = True
            logger.warning(f"Failed to initialize R2 client. Falling back to local storage: {exc}")

    def _get_client(self):
        if self.use_local or self._client is None:
            raise RuntimeError("R2 client is not configured")
        return self._client

    def _safe_local_path(self, key: str) -> Path:
        clean_key = key.lstrip("/")
        if not clean_key:
            raise ValueError("Storage key cannot be empty")

        root = LOCAL_STORAGE_ROOT.resolve()
        target = (LOCAL_STORAGE_ROOT / clean_key).resolve()
        if target != root and root not in target.parents:
            raise ValueError("Invalid storage key path")
        return target

    def upload_file(self, file_path: str, key: str) -> str:
        if self.use_local:
            destination = self._safe_local_path(key)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, destination)
            return key

        try:
            self._client.upload_file(file_path, settings.r2_bucket_name, key)
            return key
        except (ClientError, NoCredentialsError) as exc:
            logger.error(f"R2 upload_file failed for {key}: {exc}")
            raise

    def upload_fileobj(self, file_obj: BinaryIO, key: str, content_type: str | None = None) -> str:
        if self.use_local:
            destination = self._safe_local_path(key)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
            with destination.open("wb") as out:
                shutil.copyfileobj(file_obj, out)
            return key

        extra_args = {"ContentType": content_type} if content_type else None
        try:
            if extra_args:
                self._client.upload_fileobj(file_obj, settings.r2_bucket_name, key, ExtraArgs=extra_args)
            else:
                self._client.upload_fileobj(file_obj, settings.r2_bucket_name, key)
            return key
        except (ClientError, NoCredentialsError) as exc:
            logger.error(f"R2 upload_fileobj failed for {key}: {exc}")
            raise

    def get_presigned_upload_url(self, key: str, expiry: int = 900) -> dict:
        if self.use_local:
            return {
                "url": f"{_local_api_base_url()}/api/storage/local-upload",
                "key": key,
                "fields": {},
                "use_local": True,
            }

        try:
            response = self._client.generate_presigned_post(
                Bucket=settings.r2_bucket_name,
                Key=key,
                ExpiresIn=expiry,
            )
            return {
                "url": response["url"],
                "key": key,
                "fields": response.get("fields", {}),
                "use_local": False,
            }
        except ClientError as exc:
            logger.error(f"Failed to generate R2 presigned POST for {key}: {exc}")
            raise

    def get_presigned_download_url(self, key: str, expiry: int = 86400) -> str:
        if self.use_local:
            encoded_key = quote(key.lstrip("/"), safe="/")
            return f"{_local_api_base_url()}/api/storage/local/{encoded_key}"

        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.r2_bucket_name, "Key": key},
                ExpiresIn=expiry,
            )
        except ClientError as exc:
            logger.error(f"Failed to generate R2 presigned GET for {key}: {exc}")
            raise

    def download_file(self, key: str, destination_path: str) -> str:
        if self.use_local:
            source = self._safe_local_path(key)
            destination = Path(destination_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not source.exists():
                raise FileNotFoundError(f"Storage key not found: {key}")
            shutil.copy2(source, destination)
            return destination_path

        try:
            self._get_client().download_file(self.bucket_name, key, destination_path)
            return destination_path
        except ClientError as exc:
            logger.error(f"Failed to download {key}: {exc}")
            raise

    def read_text_file(self, key: str) -> str:
        if self.use_local:
            path = self._safe_local_path(key)
            if not path.exists():
                raise FileNotFoundError(f"Storage key not found: {key}")
            return path.read_text(encoding="utf-8")

        try:
            response = self._get_client().get_object(Bucket=self.bucket_name, Key=key)
            return response["Body"].read().decode("utf-8")
        except ClientError as exc:
            logger.error(f"Failed to read {key}: {exc}")
            raise

    def delete_file(self, key: str) -> bool:
        if self.use_local:
            try:
                file_path = self._safe_local_path(key)
            except ValueError:
                return False
            if not file_path.exists():
                return False
            file_path.unlink(missing_ok=True)
            self._cleanup_empty_parents(file_path.parent)
            return True

        try:
            self._client.delete_object(Bucket=settings.r2_bucket_name, Key=key)
            return True
        except ClientError as exc:
            logger.error(f"R2 delete failed for {key}: {exc}")
            return False

    def file_exists(self, key: str) -> bool:
        if self.use_local:
            try:
                file_path = self._safe_local_path(key)
            except ValueError:
                return False
            return file_path.exists() and file_path.is_file()

        try:
            self._client.head_object(Bucket=settings.r2_bucket_name, Key=key)
            return True
        except ClientError:
            return False

    def _cleanup_empty_parents(self, start: Path):
        root = LOCAL_STORAGE_ROOT.resolve()
        current = start.resolve()
        while current != root:
            if any(current.iterdir()):
                break
            os.rmdir(current)
            current = current.parent


r2_client = R2Client()
