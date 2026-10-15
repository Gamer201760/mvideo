import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from app.domain.category_guess import CategoryGuess

SCHEMA = pa.schema([
    ("sku_id", pa.int64()),
    ("category_id", pa.int64()),
    ("source", pa.string()),
    ("confidence", pa.float32()),
])
TABLE = "inferred_categories.parquet"


class ParquetCategorySink:
    def __init__(self, processed: Path, reports: Path, name: str = "category") -> None:
        self._path = processed / TABLE
        self._tmp = processed / f".{TABLE}.tmp"
        self._reports = reports
        self._name = name
        self._writer: pq.ParquetWriter | None = None

    def write(self, guesses: Sequence[CategoryGuess]) -> None:
        if self._writer is None:
            self._writer = pq.ParquetWriter(self._tmp, SCHEMA)
        self._writer.write_table(pa.table({
            "sku_id": [g.sku_id for g in guesses],
            "category_id": [g.category_id for g in guesses],
            "source": [g.source.value for g in guesses],
            "confidence": [g.confidence for g in guesses],
        }, schema=SCHEMA))

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None
            self._tmp.replace(self._path)

    def report(self, report: Mapping[str, object], markdown: str) -> None:
        self._reports.mkdir(parents=True, exist_ok=True)
        (self._reports / f"{self._name}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (self._reports / f"{self._name}.md").write_text(markdown, encoding="utf-8")
