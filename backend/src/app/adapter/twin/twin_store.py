import json
from pathlib import Path

from app.adapter.ranker.isotonic import IsotonicCalibrator

CALIBRATOR_FILE = "calibrator.json"
THRESHOLD_FILE = "threshold.json"


def save_twin_model(calibrator: IsotonicCalibrator, threshold: float, directory: Path) -> None:
    calibrator.save(directory / CALIBRATOR_FILE)
    (directory / THRESHOLD_FILE).write_text(json.dumps({"threshold": threshold}),
                                            encoding="utf-8")


def load_twin_model(directory: Path) -> tuple[IsotonicCalibrator, float]:
    calibrator = IsotonicCalibrator()
    calibrator.load(directory / CALIBRATOR_FILE)
    payload = json.loads((directory / THRESHOLD_FILE).read_text(encoding="utf-8"))
    return calibrator, float(payload["threshold"])


def has_twin_model(directory: Path) -> bool:
    return all((directory / f).exists() for f in (CALIBRATOR_FILE, THRESHOLD_FILE))
