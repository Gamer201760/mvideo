import gzip
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from app.adapter.ranker.isotonic import IsotonicCalibrator
from app.domain.inference import Vector
from app.usecase.ranker_ports import Calibrator
from app.usecase.text_ports import CatalogEntry, CategoryModel, TextIndex

ENTRIES_FILE = "entries.jsonl.gz"
VECTORS_FILE = "vectors.npy"
META_FILE = "meta.json"


class TextIndexFiles:
    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._chunks: list[np.ndarray] = []

    def exists(self) -> bool:
        return all((self._dir / f).exists() for f in (ENTRIES_FILE, VECTORS_FILE, META_FILE))

    def start(self, entries: Sequence[CatalogEntry], names: Mapping[int, str],
              embedding_model: str, dimensions: int) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        (self._dir / VECTORS_FILE).unlink(missing_ok=True)
        with gzip.open(self._dir / ENTRIES_FILE, "wt", encoding="utf-8") as handle:
            for e in entries:
                handle.write(json.dumps([e.sku_id, e.category_id, e.title, dict(e.values)],
                                        ensure_ascii=False) + "\n")
        self._chunks = []
        self._write_meta({"embedding_model": embedding_model, "dimensions": dimensions,
                          "names": {str(k): v for k, v in names.items()}, "thresholds": {},
                          "reports": {}})

    def add_vectors(self, vectors: Sequence[Vector]) -> None:
        self._chunks.append(np.asarray(vectors, dtype=np.float16))

    def finish(self) -> None:
        np.save(self._dir / VECTORS_FILE, np.concatenate(self._chunks))
        self._chunks = []

    def save_model(self, kind: str, calibrator: Calibrator, threshold: float,
                   report: Mapping[str, object]) -> None:
        if not isinstance(calibrator, IsotonicCalibrator):
            raise TypeError("only isotonic calibrators can be stored")
        calibrator.save(self._dir / f"calibrator_{kind}.json")
        meta = self._meta()
        meta["thresholds"][kind] = threshold
        meta["reports"][kind] = dict(report)
        self._write_meta(meta)

    def load(self) -> TextIndex | None:
        if not self.exists():
            return None
        meta = self._meta()
        with gzip.open(self._dir / ENTRIES_FILE, "rt", encoding="utf-8") as handle:
            entries = [CatalogEntry(int(s), int(c), str(t), dict(v))
                       for s, c, t, v in (json.loads(line) for line in handle)]
        models = {}
        for kind, threshold in meta["thresholds"].items():
            calibrator = IsotonicCalibrator()
            calibrator.load(self._dir / f"calibrator_{kind}.json")
            models[kind] = CategoryModel(calibrator, float(threshold))
        return TextIndex(entries=entries,
                         names={int(k): str(v) for k, v in meta["names"].items()},
                         models=models, embedding_model=str(meta["embedding_model"]),
                         dimensions=int(meta["dimensions"]))

    def vectors(self) -> np.ndarray:
        matrix: np.ndarray = np.load(self._dir / VECTORS_FILE).astype(np.float32)
        return matrix

    def reports(self) -> dict[str, Any]:
        reports: dict[str, Any] = self._meta().get("reports", {})
        return reports

    def _meta(self) -> dict[str, Any]:
        meta: dict[str, Any] = json.loads((self._dir / META_FILE).read_text(encoding="utf-8"))
        return meta

    def _write_meta(self, meta: Mapping[str, object]) -> None:
        (self._dir / META_FILE).write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
