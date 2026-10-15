import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from app.usecase.baseline_ports import CandidateRow, CardPrediction, PredictedValue

CANDIDATE_SCHEMA = pa.schema(
    [
        ("sku_id", pa.int64()),
        ("attribute", pa.string()),
        ("key", pa.string()),
        ("value", pa.string()),
        ("evidence", pa.string()),
        ("start", pa.int32()),
        ("end", pa.int32()),
        ("source", pa.string()),
        ("zone", pa.string()),
        ("affinity", pa.float32()),
        ("prior", pa.float32()),
        ("seller_fit", pa.int8()),
        ("slot", pa.int8()),
        ("score", pa.float32()),
        ("chosen", pa.bool_()),
    ]
)


def value_json(value: PredictedValue) -> dict[str, object]:
    return {
        "value": value.value,
        "confidence": value.confidence,
        "source": value.source,
        "sources": list(value.sources),
        "evidence": value.evidence,
        "start": value.start,
        "end": value.end,
    }


def prediction_json(prediction: CardPrediction, calibrated: bool = False) -> str:
    record = {
        "sku_id": prediction.sku_id,
        "category_id": prediction.category_id,
        "split": prediction.split,
        "confidence_calibrated": calibrated,
        "attributes": {v.attribute: value_json(v) for v in prediction.values},
        "review": {v.attribute: value_json(v) for v in prediction.review},
    }
    return json.dumps(record, ensure_ascii=False, sort_keys=True)


class FilePredictionSink:
    def __init__(
        self, out_dir: Path, name: str, candidates: bool = True, calibrated: bool = False
    ) -> None:
        self._calibrated = calibrated
        out_dir.mkdir(parents=True, exist_ok=True)
        self._predictions = (out_dir / f"{name}.predictions.jsonl").open("w", encoding="utf-8")
        self._writer = (
            pq.ParquetWriter(out_dir / f"{name}.candidates.parquet", CANDIDATE_SCHEMA)
            if candidates else None
        )

    def write(
        self, predictions: Sequence[CardPrediction], candidates: Sequence[CandidateRow]
    ) -> None:
        for prediction in predictions:
            self._predictions.write(prediction_json(prediction, self._calibrated) + "\n")
        if self._writer is not None and candidates:
            rows = [asdict(c) for c in candidates]
            self._writer.write_table(pa.Table.from_pylist(rows, schema=CANDIDATE_SCHEMA))

    def close(self) -> None:
        self._predictions.close()
        if self._writer is not None:
            self._writer.close()


class FileReportSink:
    def __init__(self, out_dir: Path, name: str) -> None:
        self._out = out_dir
        self._name = name

    def write(self, report: Mapping[str, object], markdown: str) -> None:
        self._out.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False)
        (self._out / f"{self._name}.json").write_text(payload + "\n", encoding="utf-8")
        (self._out / f"{self._name}.md").write_text(markdown, encoding="utf-8")
