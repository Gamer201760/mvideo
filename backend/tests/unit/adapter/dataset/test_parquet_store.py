from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from app.adapter.dataset.parquet_store import ParquetDatasetStore
from app.domain.catalog import GoldValue, OfferCard, Param


def card(sku: int) -> OfferCard:
    return OfferCard(sku, f"Оффер {sku}", 10, "М.Видео", True, (Param("Цвет", "черный"),))


def test_cards_join_offers_and_descriptions_both_ways(tmp_path: Path) -> None:
    descriptions = tmp_path / "sku_desc.parquet"
    pq.write_table(
        pa.table(
            {
                "sku_id": pa.array([1, 3], pa.uint64()),
                "title": ["Смартфон", "Чайник"],
                "description": ["Характеристики:\n• Цвет: черный", "Простой чайник"],
            }
        ),
        descriptions,
    )
    store = ParquetDatasetStore(tmp_path / "out", descriptions)
    store.add_offer(card(1), [GoldValue(1, "Цвет", "черный", None)])
    store.add_offer(card(2), [])
    store.close_offers()

    stats = store.attach_texts()

    rows = {r["sku_id"]: r for r in pq.read_table(tmp_path / "out" / "cards.parquet").to_pylist()}
    assert set(rows) == {1, 2, 3}
    assert rows[1]["in_catalog"] and rows[1]["has_text"] and rows[1]["has_spec_block"]
    assert rows[1]["seller_params"] == [{"name": "Цвет", "value": "черный", "unit": None}]
    assert rows[2]["in_catalog"] and not rows[2]["has_text"] and rows[2]["title"] is None
    assert not rows[3]["in_catalog"] and rows[3]["has_text"] and not rows[3]["has_spec_block"]
    assert rows[3]["seller_params"] is None
    assert (stats.cards, stats.cards_with_text, stats.cards_in_catalog) == (3, 2, 2)
    assert stats.cards_with_spec_block == 1
    gold = list(store.gold_values(frozenset({"Цвет"})))
    assert gold == [GoldValue(1, "Цвет", "черный", None)]
    assert not (tmp_path / "out" / "_offers.parquet").exists()
