import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import TextIO

from app.adapter.dataset.baseline_source import ParquetBaselineSource
from app.adapter.dataset.twin_sink import transfer_json
from app.usecase.baseline_ports import CardRecord
from app.usecase.twin_all import CardTransfers

TWINS_ALL = "twins_all"


def shard_out(work: Path, shard: str) -> Path:
    return work / f"out_{shard}"


class ShardFiles:
    def __init__(self, work: Path, count: int, stage: str) -> None:
        self._work = work
        self._count = count
        self._stage = stage

    def shards(self) -> Sequence[str]:
        return [str(i) for i in range(self._count)]

    def cards(self, shard: str, batch: int) -> Iterator[list[CardRecord]]:
        return ParquetBaselineSource(self._work / shard).cards(None, batch)

    def stage(self, shard: str) -> Iterator[Mapping[str, object]]:
        path = shard_out(self._work, shard) / f"{self._stage}_all.predictions.jsonl"
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                yield json.loads(line)


class ShardTransferFiles:
    def __init__(self, work: Path) -> None:
        self._work = work
        self._handle: TextIO | None = None

    def open(self, shard: str) -> None:
        path = shard_out(self._work, shard) / f"{TWINS_ALL}.predictions.jsonl"
        self._handle = path.open("w", encoding="utf-8")

    def write(self, records: Sequence[CardTransfers]) -> None:
        if self._handle is None:
            raise RuntimeError("shard file is not open")
        for record in records:
            attributes = {n: transfer_json(t, c) for n, (t, c) in record.transfers.items()}
            line = json.dumps({"sku_id": record.sku_id, "attributes": attributes},
                              ensure_ascii=False, sort_keys=True)
            self._handle.write(line + "\n")

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
