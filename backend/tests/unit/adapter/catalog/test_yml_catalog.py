import pickle
from pathlib import Path

import pytest

from app.adapter.catalog.pickle_stream import UnsupportedPickle, stream_list_items
from app.adapter.catalog.yml_catalog import PickledYmlCatalog
from app.domain.catalog import Category, Offer

CATALOG = {
    "yml_catalog": {
        "@date": "2026-05-13T03:00:00+0000",
        "shop": {
            "categories": {
                "category": [
                    {"@id": "1", "#text": "Телефоны"},
                    {"@id": "2", "@parentId": "1", "#text": "Смартфоны"},
                ]
            },
            "offers": {
                "offer": [
                    {
                        "@id": "30055584",
                        "@available": "true",
                        "vendor": "Samsung",
                        "model": "Galaxy S24",
                        "name": "Смартфон Samsung Galaxy S24",
                        "categories": {"categoryId": "2"},
                        "param": [
                            {"@name": "Цвет", "#text": "черный"},
                            {"@name": "Цвет_search", "#text": "черный"},
                            {"@name": "Вес_search", "@unit": "г", "#text": "168"},
                            {"@name": "Количество_search", "@unit": "шт"},
                        ],
                    },
                    {
                        "@id": "30055660",
                        "@available": "false",
                        "vendor": "Red Line",
                        "model": "MatePad",
                        "name": "Чехол",
                        "categoryId": "2",
                        "param": {"@name": "Цвет", "#text": "черный"},
                    },
                ]
            },
        },
    }
}


def write_catalog(path: Path, payload: object) -> Path:
    path.write_bytes(pickle.dumps(payload, protocol=4))
    return path


def test_stream_matches_pickle_loads_on_synthetic_catalog(tmp_path: Path) -> None:
    path = write_catalog(tmp_path / "skus.pkl", CATALOG)

    streamed = list(stream_list_items(path.read_bytes(), frozenset({"category", "offer"})))

    shop = CATALOG["yml_catalog"]["shop"]
    expected = [("category", c) for c in shop["categories"]["category"]] + [  # type: ignore[index]
        ("offer", o)
        for o in shop["offers"]["offer"]  # type: ignore[index]
    ]
    assert streamed == expected


def test_catalog_maps_categories_and_offers(tmp_path: Path) -> None:
    path = write_catalog(tmp_path / "skus.pkl", CATALOG)

    items = list(PickledYmlCatalog(path).items())

    categories = [i for i in items if isinstance(i, Category)]
    offers = [i for i in items if isinstance(i, Offer)]
    assert categories == [Category(1, None, "Телефоны"), Category(2, 1, "Смартфоны")]
    assert [o.sku_id for o in offers] == [30055584, 30055660]
    first, second = offers
    assert first.category_id == 2 and second.category_id == 2
    assert first.available and not second.available
    assert [(p.name, p.value, p.unit) for p in first.params][2] == ("Вес_search", "168", "г")
    assert first.params[3].value is None
    assert len(second.params) == 1


def test_stream_rejects_code_executing_opcodes(tmp_path: Path) -> None:
    path = write_catalog(tmp_path / "evil.pkl", {"offer": [Path("x")]})

    with pytest.raises(UnsupportedPickle):
        list(stream_list_items(path.read_bytes(), frozenset({"offer"})))
