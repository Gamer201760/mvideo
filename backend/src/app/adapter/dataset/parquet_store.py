import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from app.domain.catalog import (
    SPEC_HEADER_PATTERN,
    SPEC_LINE_PATTERN,
    SPEC_MIN_LINES,
    Category,
    GoldValue,
    OfferCard,
)
from app.domain.requirement import CategoryUsage, RequiredAttribute
from app.domain.split import Split
from app.usecase.dataset_ports import TextStats

FLUSH_ROWS = 50_000
PARAM_TYPE = pa.list_(
    pa.struct([("name", pa.string()), ("value", pa.string()), ("unit", pa.string())])
)
OFFER_SCHEMA = pa.schema(
    [
        ("sku_id", pa.int64()),
        ("offer_name", pa.string()),
        ("category_id", pa.int64()),
        ("seller", pa.string()),
        ("available", pa.bool_()),
        ("seller_params", PARAM_TYPE),
    ]
)
GOLD_SCHEMA = pa.schema(
    [
        ("sku_id", pa.int64()),
        ("attribute", pa.string()),
        ("value", pa.string()),
        ("unit", pa.string()),
    ]
)


class ParquetDatasetStore:
    def __init__(self, out_dir: Path, descriptions: Path) -> None:
        self._out = out_dir
        self._descriptions = descriptions
        out_dir.mkdir(parents=True, exist_ok=True)
        self._offers_path = out_dir / "_offers.parquet"
        self._offer_writer = pq.ParquetWriter(self._offers_path, OFFER_SCHEMA)
        self._gold_writer = pq.ParquetWriter(out_dir / "gold.parquet", GOLD_SCHEMA)
        self._offer_rows: list[dict[str, object]] = []
        self._gold_rows: list[dict[str, object]] = []

    def add_offer(self, card: OfferCard, gold: Sequence[GoldValue]) -> None:
        self._offer_rows.append(
            {
                "sku_id": card.sku_id,
                "offer_name": card.name,
                "category_id": card.category_id,
                "seller": card.seller,
                "available": card.available,
                "seller_params": [asdict(p) for p in card.seller_params],
            }
        )
        self._gold_rows.extend(asdict(value) for value in gold)
        if len(self._offer_rows) >= FLUSH_ROWS:
            self._flush()

    def close_offers(self) -> None:
        self._flush()
        self._offer_writer.close()
        self._gold_writer.close()

    def gold_values(self, attributes: frozenset[str]) -> Iterator[GoldValue]:
        file = pq.ParquetFile(self._out / "gold.parquet")
        wanted = pa.array(sorted(attributes), pa.string())
        for batch in file.iter_batches(batch_size=200_000):
            table = pa.Table.from_batches([batch])
            table = table.filter(pc.is_in(table.column("attribute"), value_set=wanted))
            for row in table.to_pylist():
                yield GoldValue(row["sku_id"], row["attribute"], row["value"], row["unit"])

    def write_categories(self, categories: Sequence[Category], paths: Mapping[int, str]) -> None:
        table = pa.table(
            {
                "category_id": pa.array([c.category_id for c in categories], pa.int64()),
                "parent_id": pa.array([c.parent_id for c in categories], pa.int64()),
                "name": [c.name for c in categories],
                "path": [paths.get(c.category_id, c.name) for c in categories],
            }
        )
        pq.write_table(table, self._out / "categories.parquet")

    def write_clicks(self, sku_clicks: Mapping[int, int], sku_category: Mapping[int, int]) -> None:
        skus = list(sku_clicks)
        table = pa.table(
            {
                "sku_id": pa.array(skus, pa.int64()),
                "clicks": pa.array([sku_clicks[s] for s in skus], pa.int64()),
                "category_id": pa.array([sku_category.get(s) for s in skus], pa.int64()),
            }
        )
        pq.write_table(table, self._out / "clicks_sku.parquet")

    def write_category_usage(self, usages: Sequence[CategoryUsage]) -> None:
        self._write_rows("clicks_category.parquet", [asdict(u) for u in usages])

    def write_splits(self, splits: Mapping[int, Split]) -> None:
        skus = sorted(splits)
        table = pa.table(
            {
                "sku_id": pa.array(skus, pa.int64()),
                "split": [str(splits[s]) for s in skus],
            }
        )
        pq.write_table(table, self._out / "splits.parquet")

    def write_required(self, required: Sequence[RequiredAttribute]) -> None:
        self._write_rows("required_attributes.parquet", [asdict(r) for r in required])

    def attach_texts(self) -> TextStats:
        offers = pq.read_table(self._offers_path)
        texts = pq.read_table(self._descriptions, columns=["sku_id", "title", "description"])
        text_ids = pc.cast(texts.column("sku_id"), pa.int64())
        description = pc.fill_null(texts.column("description"), "")
        has_spec = pc.or_(
            pc.match_substring_regex(description, SPEC_HEADER_PATTERN),
            pc.greater_equal(
                pc.count_substring_regex(description, SPEC_LINE_PATTERN), SPEC_MIN_LINES
            ),
        )
        offer_keys = pa.table(
            {"sku_id": offers.column("sku_id"), "offer_row": pa.array(range(offers.num_rows))}
        )
        text_keys = pa.table({"sku_id": text_ids, "text_row": pa.array(range(texts.num_rows))})
        keys = text_keys.join(offer_keys, "sku_id", join_type="full outer")
        matched = keys.filter(pc.is_valid(keys.column("text_row"))).sort_by("text_row")
        orphans = keys.filter(pc.is_null(keys.column("text_row")))
        offer_columns = [n for n in offers.column_names if n != "sku_id"]

        def part(
            rows: pa.Table, sku: pa.Array, title: pa.Array, desc: pa.Array, spec: pa.Array
        ) -> pa.Table:
            taken = offers.select(offer_columns).take(rows.column("offer_row"))
            return pa.table(
                {
                    "sku_id": sku,
                    **{n: taken.column(n) for n in offer_columns},
                    "title": title,
                    "description": desc,
                    "in_catalog": pc.is_valid(rows.column("offer_row")),
                    "has_text": pc.or_(pc.is_valid(title), pc.is_valid(desc)),
                    "has_spec_block": spec,
                }
            )

        if matched.num_rows == texts.num_rows:
            first = part(
                matched, text_ids, texts.column("title"), texts.column("description"), has_spec
            )
        else:
            idx = matched.column("text_row")
            first = part(
                matched,
                text_ids.take(idx),
                texts.column("title").take(idx),
                texts.column("description").take(idx),
                has_spec.take(idx),
            )
        n = orphans.num_rows
        second = part(
            orphans,
            orphans.column("sku_id"),
            pa.nulls(n, texts.schema.field("title").type),
            pa.nulls(n, texts.schema.field("description").type),
            pa.array([False] * n, pa.bool_()),
        )
        cards = pa.concat_tables([first, second.cast(first.schema)])
        pq.write_table(cards, self._out / "cards.parquet")
        self._offers_path.unlink()
        return TextStats(
            cards=cards.num_rows,
            cards_with_text=int(pc.sum(cards.column("has_text")).as_py() or 0),
            cards_in_catalog=int(pc.sum(cards.column("in_catalog")).as_py() or 0),
            cards_with_spec_block=int(pc.sum(cards.column("has_spec_block")).as_py() or 0),
        )

    def write_stats(self, stats: Mapping[str, object]) -> None:
        path = self._out / "stats.json"
        path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_rows(self, name: str, rows: list[dict[str, object]]) -> None:
        pq.write_table(pa.Table.from_pylist(rows), self._out / name)

    def _flush(self) -> None:
        if self._offer_rows:
            self._offer_writer.write_table(pa.Table.from_pylist(self._offer_rows, OFFER_SCHEMA))
            self._offer_rows = []
        if self._gold_rows:
            self._gold_writer.write_table(pa.Table.from_pylist(self._gold_rows, GOLD_SCHEMA))
            self._gold_rows = []
