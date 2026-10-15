from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from app.domain.card_text import SellerParam
from app.usecase.baseline_ports import CardRecord, GoldRecord, RequiredRecord
from app.usecase.lexicon_builder import TrainValue

CARD_COLUMNS = ["sku_id", "category_id", "seller", "title", "description", "seller_params",
                "has_text"]
GOLD_BATCH = 1_000_000
INFERRED = "inferred_categories.parquet"


class ParquetBaselineSource:
    def __init__(self, processed: Path) -> None:
        self._dir = processed
        self._splits: dict[int, str] | None = None

    def _split_map(self) -> dict[int, str]:
        if self._splits is None:
            table = pq.read_table(self._dir / "splits.parquet")
            self._splits = dict(zip(table["sku_id"].to_pylist(), table["split"].to_pylist(),
                                    strict=True))
        return self._splits

    def _skus(self, splits: frozenset[str]) -> pa.Array:
        return pa.array([s for s, name in self._split_map().items() if name in splits],
                        type=pa.int64())

    def _categories(self) -> dict[int, int]:
        table = pq.read_table(self._dir / "cards.parquet", columns=["sku_id", "category_id"],
                              filters=[("in_catalog", "=", True)])
        return {s: c for s, c in zip(table["sku_id"].to_pylist(),
                                     table["category_id"].to_pylist(), strict=True)
                if c is not None}

    def train_values(self, attributes: frozenset[str]) -> Iterator[TrainValue]:
        categories = self._categories()
        train = self._skus(frozenset({"train"}))
        wanted = pa.array(sorted(attributes), type=pa.string())
        gold = pq.ParquetFile(self._dir / "gold.parquet")
        for batch in gold.iter_batches(batch_size=GOLD_BATCH):
            mask = pc.and_(pc.is_in(batch.column(0), value_set=train),
                           pc.is_in(batch.column(1), value_set=wanted))
            kept = batch.filter(mask)
            for sku, attribute, value, unit in zip(*(kept.column(i).to_pylist() for i in range(4)),
                                                   strict=True):
                category = categories.get(sku)
                if category is not None and value:
                    yield TrainValue(category, attribute, value, unit)

    def required(self) -> Sequence[RequiredRecord]:
        table = pq.read_table(self._dir / "required_attributes.parquet",
                              columns=["category_id", "attribute", "weight"])
        return [RequiredRecord(c, a, float(w)) for c, a, w in zip(
            table["category_id"].to_pylist(), table["attribute"].to_pylist(),
            table["weight"].to_pylist(), strict=True)]

    def category_stats(self) -> Mapping[int, tuple[int, int]]:
        table = pq.read_table(self._dir / "clicks_category.parquet",
                              columns=["category_id", "clicks", "cards"])
        return {c: (k, n) for c, k, n in zip(table["category_id"].to_pylist(),
                                             table["clicks"].to_pylist(),
                                             table["cards"].to_pylist(), strict=True)}

    def seller_cards(self) -> Mapping[str, int]:
        table = pq.read_table(self._dir / "cards.parquet", columns=["seller"],
                              filters=[("in_catalog", "=", True)])
        return dict(Counter(s for s in table["seller"].to_pylist() if s))

    def gold(self, splits: frozenset[str]) -> Mapping[int, Sequence[GoldRecord]]:
        skus = self._skus(splits)
        result: dict[int, list[GoldRecord]] = defaultdict(list)
        gold = pq.ParquetFile(self._dir / "gold.parquet")
        for batch in gold.iter_batches(batch_size=GOLD_BATCH):
            kept = batch.filter(pc.is_in(batch.column(0), value_set=skus))
            for sku, attribute, value, unit in zip(*(kept.column(i).to_pylist() for i in range(4)),
                                                   strict=True):
                result[sku].append(GoldRecord(attribute, value, unit))
        return result

    def inferred_categories(self) -> dict[int, int]:
        path = self._dir / INFERRED
        if not path.exists():
            return {}
        table = pq.read_table(path, columns=["sku_id", "category_id"],
                              filters=[("source", "!=", "catalog")])
        return dict(zip(table["sku_id"].to_pylist(), table["category_id"].to_pylist(),
                        strict=True))

    def cards(self, splits: frozenset[str] | None, batch: int) -> Iterator[list[CardRecord]]:
        split_map = self._split_map()
        skus = self._skus(splits) if splits is not None else None
        inferred = self.inferred_categories() if splits is None else {}
        source = pq.ParquetFile(self._dir / "cards.parquet")
        for chunk in source.iter_batches(batch_size=batch, columns=CARD_COLUMNS):
            mask = chunk.column(CARD_COLUMNS.index("has_text"))
            if skus is not None:
                mask = pc.and_(mask, pc.is_in(chunk.column(0), value_set=skus))
            kept = chunk.filter(mask)
            if kept.num_rows:
                yield [card_record(row, split_map, inferred) for row in kept.to_pylist()]


def card_record(
    row: Mapping[str, object],
    split_map: Mapping[int, str],
    inferred: Mapping[int, int] | None = None,
) -> CardRecord:
    sku = _int(row["sku_id"])
    raw = row.get("seller_params")
    params = raw if isinstance(raw, list) else []
    seller = tuple(
        SellerParam(str(p["name"]), str(p["value"]), _text(p.get("unit")))
        for p in params
        if isinstance(p, dict) and p.get("name") and p.get("value")
    )
    category = row.get("category_id")
    resolved = _int(category) if category is not None else (inferred or {}).get(sku)
    return CardRecord(
        sku_id=sku,
        category_id=resolved,
        seller=_text(row.get("seller")),
        title=_text(row.get("title")),
        description=_text(row.get("description")),
        seller_params=seller,
        split=split_map.get(sku),
    )


def _int(value: object) -> int:
    if isinstance(value, int):
        return value
    raise TypeError(f"expected int, got {type(value).__name__}")


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None
