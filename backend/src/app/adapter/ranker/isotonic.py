import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression


class IsotonicCalibrator:
    def __init__(self) -> None:
        self._model = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        self._knots: tuple[np.ndarray, np.ndarray] | None = None

    def fit(self, scores: Sequence[float], labels: Sequence[bool]) -> None:
        self._model.fit(np.asarray(scores, dtype=np.float64), np.asarray(labels, dtype=np.float64))
        self._knots = None

    def transform(self, scores: Sequence[float]) -> Sequence[float]:
        points = np.asarray(scores, dtype=np.float64)
        if self._knots is not None:
            values: list[float] = np.interp(points, *self._knots).tolist()
            return values
        predicted: list[float] = self._model.predict(points).tolist()
        return predicted

    def save(self, path: Path) -> None:
        knots = {"x": self._model.X_thresholds_.tolist(), "y": self._model.y_thresholds_.tolist()}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(knots), encoding="utf-8")

    def load(self, path: Path) -> None:
        knots = json.loads(path.read_text(encoding="utf-8"))
        self._knots = (np.asarray(knots["x"], dtype=np.float64),
                       np.asarray(knots["y"], dtype=np.float64))
