from collections.abc import Sequence

import numpy as np

from app.adapter.twin.tfidf_index import TfidfTitleIndex
from app.domain.card_text import match_form
from app.usecase.interface import Embeddings

EMBEDDINGS_KIND = "embeddings"
TFIDF_KIND = "tfidf"


class VectorCatalogSearch:
    def __init__(self, embeddings: Embeddings, matrix: np.ndarray) -> None:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        self._matrix = (matrix / np.maximum(norms, 1e-12)).astype(np.float32)
        self._embeddings = embeddings

    @property
    def kind(self) -> str:
        return EMBEDDINGS_KIND

    async def search(self, texts: Sequence[str], k: int) -> list[list[tuple[int, float]]]:
        if not texts:
            return []
        queries = np.asarray(await self._embeddings.embed_queries(texts), dtype=np.float32)
        queries /= np.maximum(np.linalg.norm(queries, axis=1, keepdims=True), 1e-12)
        scores = queries @ self._matrix.T
        k = min(k, self._matrix.shape[0])
        result = []
        for row in scores:
            top = np.argpartition(-row, k - 1)[:k]
            ranked = sorted(((float(row[i]), int(i)) for i in top), reverse=True)
            result.append([(i, round(s, 4)) for s, i in ranked])
        return result


class TfidfCatalogSearch:
    def __init__(self, titles: Sequence[str]) -> None:
        self._index = TfidfTitleIndex(min_df=1)
        self._index.fit([match_form(t) for t in titles])

    @property
    def kind(self) -> str:
        return TFIDF_KIND

    async def search(self, texts: Sequence[str], k: int) -> list[list[tuple[int, float]]]:
        return self._index.neighbors([match_form(t) for t in texts], k)
