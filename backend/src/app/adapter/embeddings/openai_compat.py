import asyncio
from collections.abc import Sequence

import httpx
import numpy as np

from app.adapter.cache.sqlite_cache import SqliteCache
from app.domain.errors import EmbeddingsFailure
from app.domain.inference import Vector

QUERY_INSTRUCTION = (
    "Instruct: Given a product page text, retrieve catalog product titles of the same product "
    "type\nQuery: "
)


class OpenAICompatEmbeddings:
    def __init__(self, base_url: str, api_key: str, model: str, dimensions: int,
                 cache: SqliteCache | None = None, batch: int = 64, parallel: int = 4,
                 timeout_s: float = 60.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/", timeout=timeout_s, transport=transport,
            headers={"Authorization": f"Bearer {api_key}"})
        self._model = model
        self._dimensions = dimensions
        self._cache = cache
        self._batch = batch
        self._parallel = asyncio.Semaphore(parallel)
        self._spent = 0.0
        self.calls = 0

    def spent_rub(self) -> float:
        return round(self._spent, 6)

    def paid_calls(self) -> int:
        return self.calls

    async def embed_queries(self, texts: Sequence[str]) -> list[Vector]:
        return await self._embed([QUERY_INSTRUCTION + t for t in texts])

    async def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        return await self._embed(list(texts))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _embed(self, texts: list[str]) -> list[Vector]:
        keys = [SqliteCache.key("embedding", self._model, str(self._dimensions), t)
                for t in texts]
        cached = self._cache.get_many(keys) if self._cache else {}
        vectors: dict[str, Vector] = {
            k: np.frombuffer(v, dtype=np.float16).astype(np.float32).tolist()
            for k, v in cached.items()}
        unique = dict(zip(keys, texts, strict=True))
        missing = [(k, t) for k, t in unique.items() if k not in vectors]
        chunks = [missing[i:i + self._batch] for i in range(0, len(missing), self._batch)]
        for chunk, fresh in zip(chunks, await asyncio.gather(*map(self._chunk, chunks)),
                                strict=True):
            vectors.update({k: v for (k, _), v in zip(chunk, fresh, strict=True)})
        return [vectors[k] for k in keys]

    async def _chunk(self, chunk: list[tuple[str, str]]) -> list[Vector]:
        async with self._parallel:
            fresh = await self._request([t for _, t in chunk])
        if self._cache:
            self._cache.put_many({k: np.asarray(v, dtype=np.float16).tobytes()
                                  for (k, _), v in zip(chunk, fresh, strict=True)})
        return fresh

    async def _request(self, texts: list[str]) -> list[Vector]:
        payload = {"model": self._model, "input": texts, "dimensions": self._dimensions}
        try:
            response = await self._client.post("embeddings", json=payload)
            response.raise_for_status()
            body = response.json()
            rows = sorted(body["data"], key=lambda row: row["index"])
            vectors: list[Vector] = [[float(x) for x in row["embedding"]] for row in rows]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise EmbeddingsFailure(f"Embeddings request failed: {type(exc).__name__}") from exc
        if len(vectors) != len(texts):
            raise EmbeddingsFailure("Embeddings response size does not match the request")
        self.calls += 1
        self._spent += float((body.get("usage") or {}).get("cost_rub") or 0.0)
        return vectors
