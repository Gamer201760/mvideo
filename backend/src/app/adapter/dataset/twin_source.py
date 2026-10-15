import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from app.adapter.dataset.baseline_source import GOLD_BATCH
from app.adapter.dataset.ranker_source import ParquetRankerSource
from app.usecase.twin_ports import GoldRow, StageRecord, StageValue


class ParquetTwinSource(ParquetRankerSource):
    def __init__(self, processed: Path, predictions: Path) -> None:
        super().__init__(processed)
        self._predictions = predictions

    def stage_records(self, name: str) -> Mapping[int, StageRecord]:
        path = self._predictions / f"{name}.predictions.jsonl"
        records: dict[int, StageRecord] = {}
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                raw = json.loads(line)
                values = {a: _value(v) for a, v in raw.get("attributes", {}).items()}
                records[int(raw["sku_id"])] = StageRecord(raw, values)
        return records

    def gold_rows(
        self, splits: frozenset[str], attributes: frozenset[str]
    ) -> Iterator[Sequence[GoldRow]]:
        skus = self._skus(splits)
        wanted = pa.array(sorted(attributes), type=pa.string())
        gold = pq.ParquetFile(self._dir / "gold.parquet")
        for batch in gold.iter_batches(batch_size=GOLD_BATCH):
            mask = pc.and_(pc.is_in(batch.column(0), value_set=skus),
                           pc.is_in(batch.column(1), value_set=wanted))
            kept = batch.filter(mask)
            if kept.num_rows:
                yield list(zip(*(kept.column(i).to_pylist() for i in range(4)), strict=True))


def _value(raw: Mapping[str, object]) -> StageValue:
    sources = raw.get("sources")
    return StageValue(
        value=str(raw.get("value", "")),
        confidence=float(str(raw.get("confidence", 0.0))),
        source=str(raw.get("source", "")),
        sources=tuple(str(s) for s in sources) if isinstance(sources, list) else (),
        start=int(str(raw.get("start", -1))),
        end=int(str(raw.get("end", -1))),
    )
