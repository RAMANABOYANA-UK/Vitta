"""
Storage abstraction for uploaded medical bill documents.

Supports two backends:
  - "local": filesystem storage (default for development)
  - "s3":    S3-compatible object storage (MinIO, AWS S3, Cloudflare R2, etc.)

The StorageService exposes a clean async interface so the rest of the
application does not care which backend is in use.
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Union

import aiofiles

from app.config import settings

logger = logging.getLogger(__name__)

# Data can be provided as raw bytes or as a binary file-like object
StorageData = Union[bytes, BinaryIO]


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def save(self, key: str, data: StorageData, content_type: str) -> None:
        """Persist the uploaded file under the given key."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """Retrieve the stored file contents as bytes."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete the stored file."""
        raise NotImplementedError

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check whether a file exists under the given key."""
        raise NotImplementedError


class LocalStorageBackend(StorageBackend):
    """Filesystem-based storage backend."""

    def __init__(self, base_path: str | None = None) -> None:
        self.base_path = Path(base_path or settings.LOCAL_STORAGE_PATH)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info("LocalStorageBackend initialized at %s", self.base_path)

    def _resolve(self, key: str) -> Path:
        """Resolve a storage key to an absolute path, preventing traversal."""
        # Reject absolute paths and traversal attempts
        clean_key = key.lstrip("/").replace("\\", "/")
        candidate = (self.base_path / clean_key).resolve()
        if not candidate.is_relative_to(self.base_path.resolve()):
            raise ValueError(f"Invalid storage key: {key}")
        return candidate

    async def save(self, key: str, data: StorageData, content_type: str) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write in chunks to support large PDFs
        async with aiofiles.open(path, "wb") as out:
            if isinstance(data, bytes):
                await out.write(data)
            else:
                while chunk := data.read(1024 * 1024):
                    await out.write(chunk)
        logger.debug("Saved local file: %s", path)

    async def get(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {key}")
        async with aiofiles.open(path, "rb") as f:
            return await f.read()

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.exists():
            path.unlink()
            logger.debug("Deleted local file: %s", path)

    async def exists(self, key: str) -> bool:
        return self._resolve(key).exists()


class S3StorageBackend(StorageBackend):
    """S3-compatible object storage backend (boto3, thread-pool based)."""

    def __init__(self) -> None:
        import boto3

        if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
            raise ValueError(
                "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set "
                "when STORAGE_TYPE=s3"
            )
        if not settings.S3_BUCKET:
            raise ValueError("S3_BUCKET must be set when STORAGE_TYPE=s3")

        self.bucket = settings.S3_BUCKET
        self.client = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        logger.info("S3StorageBackend initialized for bucket %s", self.bucket)

    async def save(self, key: str, data: StorageData, content_type: str) -> None:
        if isinstance(data, bytes):
            body = data
        else:
            body = data.read()
        # boto3 is synchronous; offload to a thread so the event loop stays free
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
        logger.debug("Saved S3 object: %s", key)

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(
            self.client.get_object, Bucket=self.bucket, Key=key
        )
        return response["Body"].read()

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(
                self.client.head_object, Bucket=self.bucket, Key=key
            )
            return True
        except Exception:
            return False


class StorageService:
    """Facade over the configured storage backend."""

    def __init__(self) -> None:
        if settings.STORAGE_TYPE == "s3":
            self._backend: StorageBackend = S3StorageBackend()
        else:
            self._backend = LocalStorageBackend()

    @property
    def backend(self) -> StorageBackend:
        return self._backend

    async def save(self, key: str, data: StorageData, content_type: str) -> None:
        await self._backend.save(key, data, content_type)

    async def get(self, key: str) -> bytes:
        return await self._backend.get(key)

    async def delete(self, key: str) -> None:
        await self._backend.delete(key)

    async def exists(self, key: str) -> bool:
        return await self._backend.exists(key)


# Module-level singleton
storage_service = StorageService()