from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from app.domain.attribute_flow import CatalogCandidate, CatalogField, TrainProduct
from app.repository.memory.catalog_retrieval import CatalogRetrieval, add_vocabulary


def schema(category: int, path: str) -> CatalogCandidate:
    return CatalogCandidate(category, path, 0, (CatalogField("Материал", "categorical", ""),))


def test_schema_snapshot_is_stable_and_older_updates_do_not_remove_new_fields() -> None:
    original = schema(1, "Каталог / Категория")
    index = CatalogRetrieval({1: original}, ())
    snapshot = index.snapshot()
    assert index.snapshot() is snapshot
    newer = replace(original, fields=(*original.fields, CatalogField("Ширина", "numeric", "см")))
    index.remember(newer, "Категория")
    index.remember(original, "Категория")
    assert snapshot == (original,)
    assert index.snapshot()[0].fields == newer.fields
    assert index.retrieve("Категория")[0].fields == newer.fields


def test_category_retrieval_uses_title_over_decorative_description() -> None:
    schemas = {1: schema(1, "Текстиль / Фотошторы"), 2: schema(2, "Медицина / Стетоскопы")}
    products = [TrainProduct(10, 2, "Стетоскоп медицинский\nИз стали", (("Материал", "сталь"),))]
    index = CatalogRetrieval(schemas, products)
    result = index.retrieve("Фотошторы Медицинский паттерн\nСтетоскоп шприц медицинский", 2)
    assert result[0].category_id == 1
    assert result[0].example_text == ""
    assert result[1].example_values == (("Материал", "сталь"),)


def test_values_and_examples_are_category_scoped() -> None:
    schemas = {1: schema(1, "Мебель / Столы"), 2: schema(2, "Посуда / Кастрюли")}
    products = [
        TrainProduct(10, 1, "Стол кухонный", (("Материал", "дерево"),)),
        TrainProduct(11, 2, "Кастрюля кухонная", (("Материал", "сталь"),)),
    ]
    result = add_vocabulary(schemas, products)
    assert result[1].fields[0].values == ("дерево",)
    assert result[2].fields[0].values == ("сталь",)


def test_new_category_is_deduplicated_and_retrievable_with_its_fields() -> None:
    schemas = {1: schema(1, "Бытовая техника / Чайники")}
    index = CatalogRetrieval(schemas, ())
    fields = (CatalogField("Дальность хода", "numeric", "км"),)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(
            pool.map(
                lambda _: index.add_category("Транспорт / Пикапы", fields, "Электрический пикап"),
                range(5),
            )
        )
    category = results[0]
    assert category.category_id < 0
    assert {c.category_id for c in results} == {category.category_id}
    assert len(index.added_categories()) == 1
    assert len(schemas) == 1
    assert index.retrieve("Электрический пикап")[0].category_id == category.category_id
    updated = index.add_category(
        "Транспорт/Пикапы",
        (CatalogField("Мощность", "numeric", "л.с."),),
        "Пикап",
    )
    assert updated.category_id == category.category_id
    assert {f.attribute for f in updated.fields} == {"Дальность хода", "Мощность"}
    assert index.add_category("Бытовая техника/Чайники", fields, "Чайник").category_id == 1
    assert len(index.added_categories()) == 1
