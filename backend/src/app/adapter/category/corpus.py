from collections.abc import Iterator, Mapping
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from app.domain.category_guess import category_text
from app.usecase.category_ports import CategoryCard, ClickVote

TEXT_CHARS = 600
COLUMNS = ["sku_id", "category_id", "in_catalog", "has_text", "title", "description"]
CLICK_BATCH = 2_000_000


class ParquetCategoryCorpus:
    def __init__(self, processed: Path, raw: Path) -> None:
        self._dir = processed
        self._raw = raw
        self._splits: dict[int, str] | None = None

    def _split_map(self) -> dict[int, str]:
        if self._splits is None:
            table = pq.read_table(self._dir / "splits.parquet")
            self._splits = dict(zip(table["sku_id"].to_pylist(), table["split"].to_pylist(),
                                    strict=True))
        return self._splits

    def required_categories(self) -> frozenset[int]:
        table = pq.read_table(self._dir / "required_attributes.parquet", columns=["category_id"])
        return frozenset(pc.unique(table["category_id"]).to_pylist())

    def category_names(self) -> Mapping[int, str]:
        table = pq.read_table(self._dir / "categories.parquet", columns=["category_id", "path"])
        return dict(zip(table["category_id"].to_pylist(), table["path"].to_pylist(), strict=True))

    def labelled(self, splits: frozenset[str]) -> Iterator[CategoryCard]:
        for batch in self._batches(100_000, catalog_only=True):
            for card in batch:
                if card.split in splits:
                    yield card

    def cards(self, batch: int) -> Iterator[list[CategoryCard]]:
        yield from self._batches(batch, catalog_only=False)

    def click_votes(self) -> Iterator[ClickVote]:
        source = pq.ParquetFile(self._raw / "query_clicks.parquet")
        parts = []
        for batch in source.iter_batches(columns=["sku_id", "sku_seo_id"], batch_size=CLICK_BATCH):
            table = pa.table({"sku_id": pc.cast(batch.column(0), pa.int64()),
                              "category": pc.cast(batch.column(1), pa.int64())})
            parts.append(table.group_by(["sku_id", "category"]).aggregate([([], "count_all")]))
        grouped = pa.concat_tables(parts).group_by(["sku_id", "category"]).aggregate(
            [("count_all", "sum")])
        for sku, category, clicks in zip(grouped["sku_id"].to_pylist(),
                                         grouped["category"].to_pylist(),
                                         grouped["count_all_sum"].to_pylist(), strict=True):
            if category is not None:
                yield ClickVote(sku, category, clicks)

    def _batches(self, batch: int, catalog_only: bool) -> Iterator[list[CategoryCard]]:
        split_map = self._split_map()
        source = pq.ParquetFile(self._dir / "cards.parquet")
        for chunk in source.iter_batches(batch_size=batch, columns=COLUMNS):
            mask = chunk.column(COLUMNS.index("has_text"))
            if catalog_only:
                mask = pc.and_(mask, chunk.column(COLUMNS.index("in_catalog")))
            kept = chunk.filter(mask)
            if not kept.num_rows:
                continue
            titles = pc.utf8_slice_codeunits(kept.column(COLUMNS.index("title")), 0, TEXT_CHARS)
            bodies = pc.utf8_slice_codeunits(
                kept.column(COLUMNS.index("description")), 0, TEXT_CHARS)
            yield [
                CategoryCard(sku, category if in_catalog else None, split_map.get(sku),
                             category_text(title, body))
                for sku, category, in_catalog, title, body in zip(
                    kept.column(0).to_pylist(), kept.column(1).to_pylist(),
                    kept.column(2).to_pylist(), titles.to_pylist(), bodies.to_pylist(),
                    strict=True)
            ]
