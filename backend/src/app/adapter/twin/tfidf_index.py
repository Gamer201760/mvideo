from collections.abc import Sequence

import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

CHAR_FEATURES = 1 << 18
WORD_FEATURES = 100_000


class TfidfTitleIndex:
    def __init__(self, batch: int = 256, min_df: int = 2) -> None:
        self._chars = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=min_df,
                                      max_features=CHAR_FEATURES, sublinear_tf=True,
                                      dtype=np.float32)
        self._words = TfidfVectorizer(analyzer="word", token_pattern=r"[^\s]+", min_df=min_df,
                                      max_features=WORD_FEATURES, sublinear_tf=True,
                                      dtype=np.float32)
        self._batch = batch
        self._matrix: csr_matrix | None = None

    def _vectors(self, titles: Sequence[str], fit: bool) -> csr_matrix:
        if fit:
            chars, words = self._chars.fit_transform(titles), self._words.fit_transform(titles)
        else:
            chars, words = self._chars.transform(titles), self._words.transform(titles)
        matrix: csr_matrix = normalize(hstack([chars, words], format="csr", dtype=np.float32))
        return matrix

    def fit(self, titles: Sequence[str]) -> None:
        self._matrix = self._vectors(titles, fit=True).T.tocsr() if titles else None

    def neighbors(self, titles: Sequence[str], k: int) -> list[list[tuple[int, float]]]:
        if self._matrix is None or not titles:
            return [[] for _ in titles]
        size = self._matrix.shape[1]
        k = min(k, size)
        result: list[list[tuple[int, float]]] = []
        for start in range(0, len(titles), self._batch):
            queries = self._vectors(titles[start:start + self._batch], fit=False)
            scores = (queries @ self._matrix).toarray()
            top = np.argpartition(-scores, k - 1, axis=1)[:, :k]
            for row, indices in enumerate(top):
                ranked = sorted(((float(scores[row, i]), int(i)) for i in indices), reverse=True)
                result.append([(i, round(s, 4)) for s, i in ranked if s > 0])
        return result
