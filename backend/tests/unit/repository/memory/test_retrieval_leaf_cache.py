import re
from dataclasses import replace

import pytest

from app.domain.attribute_flow import CatalogCandidate, CatalogField, TrainProduct
from app.repository.memory.catalog_retrieval import CatalogRetrieval


class LegacyRetrieval(CatalogRetrieval):
    def _retrieve(self, text: str, k: int) -> tuple[CatalogCandidate, ...]:
        if k < 1:
            raise ValueError("top k must be positive")
        query = self._vectorizer.transform(
            [text.splitlines()[0][:240] if text.splitlines() else text[:240]]
        )
        scores = (self._matrix @ query.T).toarray().ravel()
        title = re.sub(r"[^a-zа-я0-9]+", " ", text.splitlines()[0].casefold()).strip()
        for category, row in self._category_rows.items():
            leaf = re.sub(
                r"[^a-zа-я0-9]+", " ", self._schemas[category].path.split("/")[-1].casefold()
            ).strip()
            if leaf and (title == leaf or title.startswith(leaf + " ")):
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
                (r for r in ranked if self._ids[r] == category and r in self._product_rows), None
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


def instances() -> tuple[CatalogRetrieval, LegacyRetrieval]:
    fields = (CatalogField("Бренд", "categorical", "", ("Brand",)),)
    schemas = {
        index: CatalogCandidate(index, path, 0, fields)
        for index, path in enumerate(
            [
                "Компьютеры / Ноутбуки",
                "Техника / Ноутбуки игровые",
                "Другое / Ноутбуки",
                "Связь / Смартфоны",
                "Природа / Ёлки",
                "Каталог / ---",
                "Другое / Телефоны",
            ],
            1,
        )
    }
    products = (TrainProduct(30, 1, "Ноутбуки Brand\nDescription", (("Бренд", "Brand"),)),)
    return CatalogRetrieval(schemas, products), LegacyRetrieval(schemas, products)


@pytest.mark.parametrize(
    "query",
    [
        "Ноутбуки",
        "Ноутбуки игровые Brand",
        "НОУТБУКИ-игровые",
        "Смартфоны Brand",
        "Ёлки",
        "Телефоны/смартфоны",
        "unrelated 123",
        "\nОписание",
        "---",
        "Ноутбукиигровые",
    ],
)
def test_leaf_cache_preserves_exact_ranking_scores_ties_and_examples(query: str) -> None:
    cached, legacy = instances()
    assert cached.retrieve(query, 7) == legacy.retrieve(query, 7)


def test_leaf_cache_stays_exact_after_new_categories_and_path_updates() -> None:
    cached, legacy = instances()
    fields = (CatalogField("Вес", "numeric", "кг"),)
    for index in (cached, legacy):
        index.add_category("Новый раздел / Ноутбуки", fields, "Ноутбуки")
        index.add_category("Новый раздел / Планшеты", fields, "Планшеты")
        index.remember(CatalogCandidate(1, "Компьютеры / Планшеты", 0, fields), "Планшеты")
        index.remember(CatalogCandidate(1, "Компьютеры / Мониторы", 0, fields), "Мониторы")
        index.remember(CatalogCandidate(30, "Новая техника / Ноутбуки", 0, fields), "Ноутбуки")
    for query in ["Ноутбуки Brand", "Планшеты Brand", "Мониторы Brand"]:
        assert cached.retrieve(query, 20) == legacy.retrieve(query, 20)


def test_batched_retrieval_is_exactly_equal_to_original_scalar_calls() -> None:
    cached, legacy = instances()
    queries = ["Ноутбуки Brand", "Ноутбуки игровые Brand", "Ёлки", "unrelated", "\nОписание"] * 9
    assert cached.retrieve_many(queries, 7) == tuple(legacy.retrieve(query, 7) for query in queries)
    cached.remember(
        CatalogCandidate(1, "Планшеты", 0, (CatalogField("Вес", "numeric", "кг"),)), "Планшеты"
    )
    legacy.remember(
        CatalogCandidate(1, "Планшеты", 0, (CatalogField("Вес", "numeric", "кг"),)), "Планшеты"
    )
    assert cached.retrieve_many(queries, 7) == tuple(legacy.retrieve(query, 7) for query in queries)
    assert cached.retrieve_many([], 7) == ()
    with pytest.raises(ValueError):
        cached.retrieve_many([], 0)
