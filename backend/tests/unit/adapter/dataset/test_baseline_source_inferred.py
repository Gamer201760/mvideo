from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from app.adapter.dataset.baseline_source import ParquetBaselineSource


def write_dataset(root: Path, with_inferred: bool) -> None:
    pq.write_table(pa.table({
        "sku_id": pa.array([1, 2, 3], pa.int64()),
        "category_id": pa.array([761, None, None], pa.int64()),
        "seller": ["М.Видео", None, None],
        "title": ["Смартфон", "Ноутбук", "Брелок"],
        "description": ["", "", ""],
        "seller_params": pa.array([[], [], []], pa.list_(pa.struct(
            [("name", pa.string()), ("value", pa.string()), ("unit", pa.string())]))),
        "has_text": [True, True, True],
        "in_catalog": [True, False, False],
    }), root / "cards.parquet")
    pq.write_table(pa.table({"sku_id": pa.array([1], pa.int64()), "split": ["test"]}),
                   root / "splits.parquet")
    if with_inferred:
        pq.write_table(pa.table({
            "sku_id": pa.array([1, 2], pa.int64()),
            "category_id": pa.array([999, 987], pa.int64()),
            "source": ["catalog", "classifier"],
            "confidence": pa.array([1.0, 0.8], pa.float32()),
        }), root / "inferred_categories.parquet")


def categories(root: Path, splits: frozenset[str] | None) -> dict[int, int | None]:
    source = ParquetBaselineSource(root)
    return {c.sku_id: c.category_id for batch in source.cards(splits, 10) for c in batch}


def test_all_cards_take_inferred_category_but_catalog_wins(tmp_path: Path) -> None:
    write_dataset(tmp_path, with_inferred=True)
    assert categories(tmp_path, None) == {1: 761, 2: 987, 3: None}


def test_evaluation_splits_ignore_inferred_categories(tmp_path: Path) -> None:
    write_dataset(tmp_path, with_inferred=True)
    assert categories(tmp_path, frozenset({"test"})) == {1: 761}


def test_without_inferred_table_nothing_changes(tmp_path: Path) -> None:
    write_dataset(tmp_path, with_inferred=False)
    assert categories(tmp_path, None) == {1: 761, 2: None, 3: None}
