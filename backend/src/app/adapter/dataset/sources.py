from collections.abc import Iterator, Mapping
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from app.usecase.dataset_ports import QueryStat

SKU = "sku_id"
QUERY = "toValidUTF8(query_text)"
MERGE_EVERY = 16


class ParquetDescriptions:
    def __init__(self, path: Path) -> None:
        self._path = path

    def sku_ids(self) -> set[int]:
        column = pq.read_table(self._path, columns=[SKU]).column(SKU)
        return {int(value) for value in column.to_pylist()}


class ParquetClicks:
    def __init__(self, path: Path) -> None:
        self._path = path

    def sku_clicks(self) -> dict[int, int]:
        counts = pc.value_counts(pq.read_table(self._path, columns=[SKU]).column(SKU))
        values = counts.field("values").to_pylist()
        totals = counts.field("counts").to_pylist()
        return {int(v): int(c) for v, c in zip(values, totals, strict=True)}

    def category_queries(self, sku_category: Mapping[int, int]) -> Iterator[QueryStat]:
        mapping = pa.table(
            {
                SKU: pa.array(list(sku_category.keys()), pa.uint64()),
                "category_id": pa.array(list(sku_category.values()), pa.int64()),
            }
        )
        file = pq.ParquetFile(self._path)
        partials: list[pa.Table] = []
        merged: pa.Table | None = None
        for group in range(file.num_row_groups):
            batch = file.read_row_group(group, columns=[SKU, QUERY])
            batch = batch.rename_columns([SKU, "query"]).join(mapping, SKU, join_type="inner")
            grouped = batch.group_by(["category_id", "query"]).aggregate([([], "count_all")])
            partials.append(
                pa.table(
                    {
                        "category_id": grouped.column("category_id"),
                        "query": grouped.column("query"),
                        "clicks": grouped.column("count_all"),
                    }
                )
            )
            if len(partials) >= MERGE_EVERY:
                merged = _merge(merged, partials)
                partials = []
        merged = _merge(merged, partials)
        if merged is None:
            return
        for record in merged.to_batches(max_chunksize=100_000):
            categories = record.column("category_id").to_pylist()
            queries = record.column("query").to_pylist()
            clicks = record.column("clicks").to_pylist()
            for category, query, count in zip(categories, queries, clicks, strict=True):
                if query:
                    yield QueryStat(int(category), str(query), int(count))


def _merge(merged: pa.Table | None, partials: list[pa.Table]) -> pa.Table | None:
    tables = list(partials)
    if merged is not None:
        tables.append(merged)
    if not tables:
        return merged
    grouped = (
        pa.concat_tables(tables).group_by(["category_id", "query"]).aggregate([("clicks", "sum")])
    )
    return pa.table(
        {
            "category_id": grouped.column("category_id"),
            "query": grouped.column("query"),
            "clicks": grouped.column("clicks_sum"),
        }
    )
