import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

from app.adapter.dataset.twin_all_files import TWINS_ALL

Raw = Mapping[str, object]


def _lines(path: Path) -> Iterator[Raw]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


class JsonlAllCardsSource:
    def __init__(
        self, shards: Sequence[Path], name: str, predictions: Path, twins: str = TWINS_ALL
    ) -> None:
        self._shards = shards
        self._name = name
        self._predictions = predictions
        self._twins = twins

    def pairs(self) -> Iterator[tuple[Raw, Raw, Raw | None]]:
        for shard in self._shards:
            ranker = _lines(shard / f"{self._name}_all.predictions.jsonl")
            baseline = _lines(shard / f"{self._name}_all_baseline.predictions.jsonl")
            twin_path = shard / f"{self._twins}.predictions.jsonl"
            if twin_path.exists():
                rows: Iterator[tuple[Raw, Raw, Raw | None]] = zip(
                    ranker, baseline, _lines(twin_path), strict=True)
            else:
                rows = ((left, right, None) for left, right in zip(ranker, baseline, strict=True))
            for left, right, twin in rows:
                sku = left.get("sku_id")
                if sku != right.get("sku_id") or (twin is not None and twin.get("sku_id") != sku):
                    raise ValueError(f"shard {shard} is out of order at {sku}")
                yield left, right, twin

    def records(self, name: str) -> Mapping[int, Raw]:
        path = self._predictions / f"{name}.predictions.jsonl"
        if not path.exists():
            return {}
        return {int(str(r["sku_id"])): r for r in _lines(path)}


class JsonlRecordSink:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("w", encoding="utf-8")

    def write(self, records: Sequence[Raw]) -> None:
        for record in records:
            self._handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def close(self) -> None:
        self._handle.close()
