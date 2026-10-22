from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.adapter.dataset.parquet_store import ParquetDatasetStore
from app.domain.catalog import OfferCard


@pytest.mark.parametrize("threads", [1, 2, 4])
def test_outer_join_keeps_description_order_then_catalog_only_order(
    tmp_path: Path, threads: int
) -> None:
    descriptions = tmp_path / "descriptions.parquet"
    pq.write_table(
        pa.table(
            {
                "sku_id": pa.array([80, 999, 30], pa.int64()),
                "title": ["First", "Outside catalog", "Third"],
                "description": ["Text"] * 3,
            }
        ),
        descriptions,
    )
    previous_threads = pa.cpu_count()
    try:
        pa.set_cpu_count(threads)
        store = ParquetDatasetStore(tmp_path / "processed", descriptions)
        for sku in [90, 30, 80, 10, 70, 20]:
            store.add_offer(OfferCard(sku, str(sku), 1, None, True, ()), ())
        store.close_offers()
        stats = store.attach_texts()
    finally:
        pa.set_cpu_count(previous_threads)
    rows = pq.read_table(tmp_path / "processed/cards.parquet").to_pylist()
    assert [row["sku_id"] for row in rows] == [80, 999, 30, 90, 10, 70, 20]
    assert stats.cards == 7 and stats.cards_with_text == 3 and stats.cards_in_catalog == 6
    assert rows[1]["category_id"] is None
    assert all(row["title"] is None and row["has_text"] is False for row in rows[3:])
