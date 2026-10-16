"""Object storage for generated documents (docs/BACKEND_BUILD_STEPS.md
Step 38) — MinIO, matching docker-compose.yml's existing service.

An ABC (same shape as EmbeddingClient/LLMClient) rather than using the
`minio` package's client directly everywhere, so tests don't need a real
MinIO container just to prove the wiring logic around it. The official
`minio` SDK is synchronous; `asyncio.to_thread` keeps it from blocking
the event loop in an otherwise all-async codebase, the same reasoning
Step 24's embedding client and Step 28's LLM client don't need since
`httpx.AsyncClient` is already async natively.
"""

from __future__ import annotations

import asyncio
import io
from abc import ABC, abstractmethod

from minio import Minio


class ObjectStorageClient(ABC):
    @abstractmethod
    async def put(self, bucket: str, key: str, data: bytes, content_type: str) -> str:
        """Write data, returning a storage_ref (applications.generated_documents.storage_ref)."""


class MinioStorageClient(ObjectStorageClient):
    def __init__(self, client: Minio) -> None:
        self.client = client

    async def put(
        self, bucket: str, key: str, data: bytes, content_type: str = "text/plain"
    ) -> str:
        await asyncio.to_thread(self._put_sync, bucket, key, data, content_type)
        return f"{bucket}/{key}"

    def _put_sync(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)
        self.client.put_object(
            bucket, key, io.BytesIO(data), length=len(data), content_type=content_type
        )
