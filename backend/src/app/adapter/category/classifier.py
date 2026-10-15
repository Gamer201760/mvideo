import re
from collections.abc import Sequence
from itertools import pairwise

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer, TfidfTransformer
from sklearn.linear_model import SGDClassifier

from app.domain.category_guess import Ranked

FEATURES = 2**16
RANK_BATCH = 5_000
_WORDS = re.compile(r"\w+")


def analyze(text: str) -> list[str]:
    tokens = _WORDS.findall(text)
    grams = [f"w {token}" for token in tokens]
    grams += [f"b {left} {right}" for left, right in pairwise(tokens)]
    for token in tokens:
        padded = f" {token} "
        for size in (3, 4):
            grams += [padded[i:i + size] for i in range(len(padded) - size + 1)]
    return grams


class TfidfLinearClassifier:
    def __init__(self, seed: int = 0, jobs: int = 3, epochs: int = 8) -> None:
        self._vectorizer = HashingVectorizer(analyzer=analyze, n_features=FEATURES,
                                             alternate_sign=False, norm=None,
                                             dtype=np.float64)
        self._tfidf = TfidfTransformer(sublinear_tf=True)
        self._model = SGDClassifier(loss="log_loss", alpha=2e-6, max_iter=epochs, tol=None,
                                    n_jobs=jobs, random_state=seed)
        self._classes: np.ndarray | None = None

    def _features(self, texts: Sequence[str]) -> object:
        return self._tfidf.transform(self._vectorizer.transform(texts), copy=False)

    def fit(self, texts: Sequence[str], labels: Sequence[int]) -> None:
        counts = self._vectorizer.transform(texts)
        self._tfidf.fit(counts)
        matrix = self._tfidf.transform(counts, copy=False)
        del counts
        self._model.fit(matrix, np.asarray(labels))
        self._classes = self._model.classes_

    def rank(self, texts: Sequence[str], k: int) -> list[Ranked]:
        if self._classes is None:
            raise RuntimeError("classifier is not fitted")
        ranked: list[Ranked] = []
        for start in range(0, len(texts), RANK_BATCH):
            probabilities = self._model.predict_proba(
                self._features(texts[start:start + RANK_BATCH]))
            top = np.argsort(-probabilities, axis=1)[:, :k]
            for row, indices in zip(probabilities, top, strict=True):
                ranked.append([(int(self._classes[i]), float(row[i])) for i in indices])
        return ranked
