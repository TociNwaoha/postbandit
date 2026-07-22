import logging
import os
import shutil
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, NoCredentialsError

from app.config import settings

logger = logging.getLogger(__name__)

LOCAL_STORAGE_ROOT = Path("/tmp/clipbandit-storage")
THUMBNAIL_DIR = Path(os.environ.get("THUMBNAIL_DIR", "/data/thumbnails"))
STORAGE_TEMPORARILY_UNAVAILABLE_MESSAGE = (
    "Source video is temporarily unavailable from storage. Try again after the storage download limit resets."
)


class StorageUnavailableError(RuntimeError):
    """Raised when the configured object store refuses a read for a currently unavailable object."""

    def __init__(self, key: str, operation: str, *, cause: Exception | None = None):
        super().__init__(STORAGE_TEMPORARILY_UNAVAILABLE_MESSAGE)
        self.key = key
        self.operation = operation
        self.__cause__ = cause


def _local_api_base_url() -> str:
    configured = (settings.backend_public_url or "").strip().rstrip("/")
    if configured:
        return configured
    return "http://localhost:8000"


class ObjectStorageClient:
    """Backblaze B2-backed object storage with temporary local read fallback."""

    def __init__(self):
        self._client = None
        self.bucket_name = settings.b2_bucket_name
        LOCAL_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
        self._init_client()

    def _is_placeholder(self, value: str | None) -> bool:
        if value is None:
            return True
        normalized = value.strip().lower()
        return normalized == "" or normalized == "placeholder" or "placeholder" in normalized

    @property
    def configured(self) -> bool:
        return self._client is not None and not any(
            self._is_placeholder(value)
            for value in (
                settings.b2_key_id,
                settings.b2_application_key,
                settings.b2_bucket_name,
                settings.b2_endpoint_url,
                settings.b2_region,
            )
        )

    @property
    def use_local(self) -> bool:
        # Kept for existing response schemas. New writes never use local permanent storage.
        return False

    def _init_client(self):
        if any(
            self._is_placeholder(value)
            for value in (
                settings.b2_key_id,
                settings.b2_application_key,
                settings.b2_bucket_name,
                settings.b2_endpoint_url,
                settings.b2_region,
            )
        ):
            logger.warning("B2 storage is not configured. Writes will fail; local read fallback remains available.")
            return

        self._client = boto3.client(
            "s3",
            endpoint_url=settings.b2_endpoint_url,
            aws_access_key_id=settings.b2_key_id,
            aws_secret_access_key=settings.b2_application_key,
            region_name=settings.b2_region,
            config=Config(signature_version="s3v4"),
        )

    def _get_client(self):
        if self._client is None:
            raise RuntimeError("Backblaze B2 object storage is not configured")
        return self._client

    def local_fallback_path(self, key: str) -> Path:
        clean_key = key.lstrip("/")
        if not clean_key:
            raise ValueError("Storage key cannot be empty")

        root = LOCAL_STORAGE_ROOT.resolve()
        target = (LOCAL_STORAGE_ROOT / clean_key).resolve()
        if target != root and root not in target.parents:
            raise ValueError("Invalid storage key path")
        return target

    def local_thumbnail_path(self, key: str) -> Path:
        clean_key = key.lstrip("/")
        if not clean_key:
            raise ValueError("Storage key cannot be empty")

        root = THUMBNAIL_DIR.resolve()
        target = (THUMBNAIL_DIR / clean_key).resolve()
        if target != root and root not in target.parents:
            raise ValueError("Invalid thumbnail key path")
        return target

    def _local_file_exists(self, key: str) -> bool:
        try:
            file_path = self.local_fallback_path(key)
        except ValueError:
            return False
        return file_path.exists() and file_path.is_file()

    def _log_local_fallback(self, key: str, operation: str):
        logger.warning(
            "[storage_local_fallback] operation=%s key=%s local_root=%s",
            operation,
            key,
            LOCAL_STORAGE_ROOT,
        )

    def _is_not_found(self, exc: ClientError) -> bool:
        error = exc.response.get("Error", {}) if exc.response else {}
        code = str(error.get("Code") or "").lower()
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") if exc.response else None
        return status == 404 or code in {"404", "nosuchkey", "notfound"}

    def _is_forbidden(self, exc: ClientError) -> bool:
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") if exc.response else None
        return status == 403

    def upload_file(self, file_path: str, key: str) -> str:
        try:
            self._get_client().upload_file(file_path, self.bucket_name, key)
            return key
        except (ClientError, NoCredentialsError) as exc:
            logger.error("B2 upload_file failed for %s: %s", key, exc)
            raise

    def upload_fileobj(self, file_obj: BinaryIO, key: str, content_type: str | None = None) -> str:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        extra_args = {"ContentType": content_type} if content_type else None
        try:
            if extra_args:
                self._get_client().upload_fileobj(file_obj, self.bucket_name, key, ExtraArgs=extra_args)
            else:
                self._get_client().upload_fileobj(file_obj, self.bucket_name, key)
            return key
        except (ClientError, NoCredentialsError) as exc:
            logger.error("B2 upload_fileobj failed for %s: %s", key, exc)
            raise

    def get_presigned_upload_url(self, key: str, expiry: int = 900) -> dict:
        try:
            response = self._get_client().generate_presigned_post(
                Bucket=self.bucket_name,
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
            logger.error("Failed to generate B2 presigned POST for %s: %s", key, exc)
            raise

    def get_presigned_download_url(self, key: str, expiry: int = 86400) -> str:
        if self.remote_file_exists(key):
            try:
                return self._get_client().generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket_name, "Key": key},
                    ExpiresIn=expiry,
                )
            except ClientError as exc:
                logger.error("Failed to generate B2 presigned GET for %s: %s", key, exc)
                raise

        if self._local_file_exists(key):
            self._log_local_fallback(key, "presigned_download_url")
            encoded_key = quote(key.lstrip("/"), safe="/")
            return f"{_local_api_base_url()}/api/storage/local/{encoded_key}"

        raise FileNotFoundError(f"Storage key not found: {key}")

    def save_thumbnail_locally(self, source_path: str, thumbnail_key: str) -> str:
        destination = self.local_thumbnail_path(thumbnail_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        return str(destination)

    def get_thumbnail_url(self, thumbnail_key: str | None) -> str | None:
        if not thumbnail_key:
            return None
        try:
            local_path = self.local_thumbnail_path(thumbnail_key)
        except ValueError:
            return None
        if not local_path.exists() or not local_path.is_file():
            return None
        encoded_key = quote(thumbnail_key.lstrip("/"), safe="/")
        return f"/thumbnails/{encoded_key}"

    def download_file(self, key: str, destination_path: str) -> str:
        destination = Path(destination_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._get_client().download_file(self.bucket_name, key, destination_path)
            return destination_path
        except ClientError as exc:
            if (self._is_not_found(exc) or self._is_forbidden(exc)) and self._local_file_exists(key):
                self._log_local_fallback(key, "download_file")
                shutil.copy2(self.local_fallback_path(key), destination)
                return destination_path
            if self._is_forbidden(exc):
                logger.warning(
                    "B2 download unavailable operation=download_file key=%s status=403",
                    key,
                )
                raise StorageUnavailableError(key, "download_file", cause=exc) from exc
            logger.error("Failed to download %s from B2: %s", key, exc)
            raise
        except RuntimeError:
            if self._local_file_exists(key):
                self._log_local_fallback(key, "download_file_unconfigured")
                shutil.copy2(self.local_fallback_path(key), destination)
                return destination_path
            raise

    def read_text_file(self, key: str) -> str:
        try:
            response = self._get_client().get_object(Bucket=self.bucket_name, Key=key)
            return response["Body"].read().decode("utf-8")
        except ClientError as exc:
            if (self._is_not_found(exc) or self._is_forbidden(exc)) and self._local_file_exists(key):
                self._log_local_fallback(key, "read_text_file")
                return self.local_fallback_path(key).read_text(encoding="utf-8")
            if self._is_forbidden(exc):
                logger.warning(
                    "B2 read unavailable operation=read_text_file key=%s status=403",
                    key,
                )
                raise StorageUnavailableError(key, "read_text_file", cause=exc) from exc
            logger.error("Failed to read %s from B2: %s", key, exc)
            raise
        except RuntimeError:
            if self._local_file_exists(key):
                self._log_local_fallback(key, "read_text_file_unconfigured")
                return self.local_fallback_path(key).read_text(encoding="utf-8")
            raise

    def delete_file(self, key: str) -> bool:
        deleted = False
        try:
            self._get_client().delete_object(Bucket=self.bucket_name, Key=key)
            deleted = True
        except RuntimeError:
            logger.warning("B2 delete skipped because object storage is not configured key=%s", key)
        except ClientError as exc:
            logger.error("B2 delete failed for %s: %s", key, exc)

        try:
            local_path = self.local_fallback_path(key)
        except ValueError:
            return deleted
        if local_path.exists():
            local_path.unlink(missing_ok=True)
            self._cleanup_empty_parents(local_path.parent)
            deleted = True
        try:
            thumbnail_path = self.local_thumbnail_path(key)
        except ValueError:
            return deleted
        if thumbnail_path.exists():
            thumbnail_path.unlink(missing_ok=True)
            self._cleanup_empty_parents(thumbnail_path.parent, root=THUMBNAIL_DIR)
            deleted = True
        return deleted

    def delete_local_fallback_file(self, key: str) -> bool:
        local_path = self.local_fallback_path(key)
        if not local_path.exists() or not local_path.is_file():
            return False
        local_path.unlink(missing_ok=True)
        self._cleanup_empty_parents(local_path.parent)
        return True

    def remote_file_exists(self, key: str) -> bool:
        try:
            self._get_client().head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError:
            return False
        except RuntimeError:
            return False

    def remote_file_size(self, key: str) -> int | None:
        try:
            response = self._get_client().head_object(Bucket=self.bucket_name, Key=key)
            size = response.get("ContentLength")
            return int(size) if size is not None else None
        except ClientError as exc:
            if self._is_not_found(exc):
                return None
            if self._is_forbidden(exc):
                logger.warning(
                    "B2 read unavailable operation=remote_file_size key=%s status=403",
                    key,
                )
                raise StorageUnavailableError(key, "remote_file_size", cause=exc) from exc
            raise

    def file_exists(self, key: str) -> bool:
        if self.remote_file_exists(key):
            return True
        if self._local_file_exists(key):
            self._log_local_fallback(key, "file_exists")
            return True
        return False

    def _cleanup_empty_parents(self, start: Path, *, root: Path = LOCAL_STORAGE_ROOT):
        root = root.resolve()
        current = start.resolve()
        while current != root:
            if any(current.iterdir()):
                break
            os.rmdir(current)
            current = current.parent


object_storage_client = ObjectStorageClient()
