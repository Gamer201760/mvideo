import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import replace
from threading import RLock

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import vstack
from sklearn.feature_extraction.text import TfidfVectorizer

from app.domain.attribute_flow import CatalogCandidate, CatalogField, TrainProduct
from app.domain.card_text import match_form
from app.domain.category_path import category_path


class CatalogRetrieval:
    def __init__(
        self,
        schemas: Mapping[int, CatalogCandidate],
        products: Sequence[TrainProduct],
    ) -> None:
        if not schemas:
            raise ValueError("category schemas are empty")
        self._schemas = dict(schemas)
        self._snapshot = tuple(self._schemas.values())
        self._lock = RLock()
        self._added: set[int] = {c for c in schemas if c < 0}
        self._category_rows = {category: row for row, category in enumerate(schemas)}
        self._leaf_rows: dict[str, set[int]] = defaultdict(set)
        self._row_leaves: dict[int, str] = {}
        for category in schemas:
            self._index_leaf(category)
        self._paths = {match_form(c.path).strip(): c.category_id for c in schemas.values()}
        self._products = products
        self._ids = list(schemas)
        documents = [schemas[category].path for category in self._ids]
        self._product_rows: dict[int, int] = {}
        for index, product in enumerate(products):
            if product.category_id in schemas:
                self._product_rows[len(documents)] = index
                self._ids.append(product.category_id)
                title = product.text.splitlines()[0]
                documents.append(title + " " + schemas[product.category_id].path)
        self._vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            max_features=60_000,
            sublinear_tf=True,
        )
        self._matrix = self._vectorizer.fit_transform(documents).tocsr()

    def retrieve(self, text: str, k: int = 3) -> tuple[CatalogCandidate, ...]:
        with self._lock:
            return self._retrieve(text, k)

    def retrieve_many(
        self, texts: Sequence[str], k: int = 3
    ) -> tuple[tuple[CatalogCandidate, ...], ...]:
        if k < 1:
            raise ValueError("top k must be positive")
        if not texts:
            return ()
        with self._lock:
            queries = self._vectorizer.transform(
                [text.splitlines()[0][:240] if text.splitlines() else text[:240] for text in texts]
            )
            scores = (self._matrix @ queries.T).toarray()
            return tuple(self._rank(text, scores[:, index], k) for index, text in enumerate(texts))

    def snapshot(self) -> tuple[CatalogCandidate, ...]:
        with self._lock:
            return self._snapshot

    def added_categories(self) -> tuple[CatalogCandidate, ...]:
        with self._lock:
            return tuple(self._schemas[category] for category in sorted(self._added))

    def add_category(
        self, path: str, fields: tuple[CatalogField, ...], title: str
    ) -> CatalogCandidate:
        path = category_path(path)
        if not path or len(path) > 200 or not fields:
            raise ValueError("new category requires a path and supported fields")
        with self._lock:
            key = match_form(path).strip()
            category = self._paths.get(key)
            if category is not None and category not in self._added:
                return self._schemas[category]
            if category is None:
                category = min(0, *self._schemas) - 1
                vector = self._vectorizer.transform([f"{title[:240]} {path}"])
                self._matrix = vstack((self._matrix, vector), format="csr")
                self._category_rows[category] = len(self._ids)
                self._ids.append(category)
                self._paths[key] = category
                self._added.add(category)
            previous = self._schemas.get(category)
            merged = {match_form(f.attribute): f for f in previous.fields} if previous else {}
            for field in fields:
                merged.setdefault(match_form(field.attribute), field)
            result = CatalogCandidate(category, path, 0, tuple(merged.values()))
            self._schemas[category] = result
            self._index_leaf(category)
            self._snapshot = tuple(self._schemas.values())
            return result

    def remember(self, category: CatalogCandidate, title: str) -> None:
        with self._lock:
            identifier = category.category_id
            previous = self._schemas.get(identifier)
            if previous is not None:
                fields = {f.attribute.casefold(): f for f in previous.fields}
                for field in category.fields:
                    fields.setdefault(field.attribute.casefold(), field)
                category = replace(category, fields=tuple(fields.values()))
            if identifier not in self._schemas:
                vector = self._vectorizer.transform([f"{title[:240]} {category.path}"])
                self._matrix = vstack((self._matrix, vector), format="csr")
                self._category_rows[identifier] = len(self._ids)
                self._ids.append(identifier)
            self._schemas[identifier] = category
            self._index_leaf(identifier)
            self._snapshot = tuple(self._schemas.values())
            self._paths[match_form(category.path).strip()] = identifier
            if identifier < 0:
                self._added.add(identifier)

    def _index_leaf(self, category: int) -> None:
        row = self._category_rows[category]
        previous = self._row_leaves.get(row)
        if previous is not None:
            self._leaf_rows[previous].discard(row)
            if not self._leaf_rows[previous]:
                del self._leaf_rows[previous]
        leaf = re.sub(
            r"[^a-zа-я0-9]+", " ", self._schemas[category].path.split("/")[-1].casefold()
        ).strip()
        self._row_leaves[row] = leaf
        if leaf:
            self._leaf_rows[leaf].add(row)

    def _retrieve(self, text: str, k: int) -> tuple[CatalogCandidate, ...]:
        if k < 1:
            raise ValueError("top k must be positive")
        query = self._vectorizer.transform(
            [text.splitlines()[0][:240] if text.splitlines() else text[:240]]
        )
        scores = (self._matrix @ query.T).toarray().ravel()
        return self._rank(text, scores, k)

    def _rank(self, text: str, scores: NDArray[np.float64], k: int) -> tuple[CatalogCandidate, ...]:
        title = re.sub(r"[^a-zа-я0-9]+", " ", text.splitlines()[0].casefold()).strip()
        words = title.split()
        for length in range(1, len(words) + 1):
            for row in self._leaf_rows.get(" ".join(words[:length]), ()):
                scores[row] += 1
        ranked = scores.argsort()[::-1]
        found: list[CatalogCandidate] = []
        seen: set[int] = set()
        for row in ranked:
            category = self._ids[row]
            if category in seen or scores[row] <= 0:
                continue
            seen.add(category)
            schema = self._schemas[category]
            example_row = next(
                (r for r in ranked if self._ids[r] == category and r in self._product_rows),
                None,
            )
            example = (
                self._products[self._product_rows[example_row]] if example_row is not None else None
            )
            found.append(
                replace(
                    schema,
                    score=round(float(scores[row]), 4),
                    example_text=example.text[:1200] if example else "",
                    example_values=tuple(
                        (a, v)
                        for a, v in example.values
                        if a in {f.attribute for f in schema.fields}
                    )
                    if example
                    else (),
                )
            )
            if len(found) == k:
                break
        return tuple(found)


def add_vocabulary(
    schemas: Mapping[int, CatalogCandidate],
    products: Sequence[TrainProduct],
) -> dict[int, CatalogCandidate]:
    values: dict[tuple[int, str], Counter[str]] = defaultdict(Counter)
    for product in products:
        for attribute, value in product.values:
            if attribute not in {"Бренд", "Модель"}:
                values[product.category_id, attribute][value] += 1
    return {
        category: replace(
            schema,
            fields=tuple(
                replace(
                    field,
                    values=tuple(v for v, _ in values[category, field.attribute].most_common(8)),
                )
                for field in schema.fields
            ),
        )
        for category, schema in schemas.items()
    }
