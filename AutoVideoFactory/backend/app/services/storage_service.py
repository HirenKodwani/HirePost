from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Optional

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger("autovideofactory.services.storage")


class StorageService(ABC):
    @abstractmethod
    async def upload(self, local_path: str, remote_path: str) -> str:
        ...

    @abstractmethod
    async def download(self, remote_path: str, local_path: str) -> str:
        ...

    @abstractmethod
    async def delete(self, remote_path: str) -> None:
        ...

    @abstractmethod
    async def exists(self, remote_path: str) -> bool:
        ...

    @abstractmethod
    def get_public_url(self, remote_path: str) -> str:
        ...


class LocalStorageService(StorageService):
    def __init__(self) -> None:
        self._base_dir = Path(settings.data_dir).resolve()

    async def upload(self, local_path: str, remote_path: str) -> str:
        dest = self._base_dir / remote_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)
        logger.debug(f"Local copy: {local_path} -> {dest}")
        return str(dest)

    async def download(self, remote_path: str, local_path: str) -> str:
        src = self._base_dir / remote_path
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, local_path)
        return local_path

    async def delete(self, remote_path: str) -> None:
        path = self._base_dir / remote_path
        if path.exists():
            path.unlink()

    async def exists(self, remote_path: str) -> bool:
        return (self._base_dir / remote_path).exists()

    def get_public_url(self, remote_path: str) -> str:
        return str(self._base_dir / remote_path)


class GCSStorageService(StorageService):
    def __init__(self, bucket_name: str = "") -> None:
        from google.cloud import storage

        self._bucket_name = bucket_name or settings.gcs_bucket_name or ""
        self._client = storage.Client()
        self._bucket = self._client.bucket(self._bucket_name)

    async def upload(self, local_path: str, remote_path: str) -> str:
        from google.cloud import exceptions

        blob = self._bucket.blob(remote_path)
        blob.upload_from_filename(local_path)
        logger.debug(f"GCS upload: {local_path} -> gs://{self._bucket_name}/{remote_path}")
        return f"gs://{self._bucket_name}/{remote_path}"

    async def download(self, remote_path: str, local_path: str) -> str:
        blob = self._bucket.blob(remote_path)
        blob.download_to_filename(local_path)
        return local_path

    async def delete(self, remote_path: str) -> None:
        blob = self._bucket.blob(remote_path)
        blob.delete()

    async def exists(self, remote_path: str) -> bool:
        blob = self._bucket.blob(remote_path)
        return blob.exists()

    def get_public_url(self, remote_path: str) -> str:
        return f"https://storage.googleapis.com/{self._bucket_name}/{remote_path}"


def get_storage_service() -> StorageService:
    if settings.storage_provider == "gcs":
        return GCSStorageService()
    return LocalStorageService()


storage = get_storage_service()
