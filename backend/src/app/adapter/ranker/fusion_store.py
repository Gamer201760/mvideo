import json
from pathlib import Path

from app.adapter.ranker.catboost_model import MODEL_FILE, CatBoostScoreModel
from app.adapter.ranker.isotonic import IsotonicCalibrator
from app.domain.fusion import SOURCES, FusionRules
from app.usecase.final import FusionModel
from app.usecase.ranker_ports import Calibrator

RULES_FILE = "rules.json"
CALIBRATOR_FILE = "calibrator.json"
THRESHOLD_FILE = "threshold.json"


def save_ranker(model: CatBoostScoreModel, calibrator: IsotonicCalibrator, threshold: float,
                directory: Path) -> None:
    model.save(directory)
    calibrator.save(directory / CALIBRATOR_FILE)
    (directory / THRESHOLD_FILE).write_text(json.dumps({"threshold": threshold}),
                                            encoding="utf-8")


def load_ranker(directory: Path, threads: int = 1) -> tuple[CatBoostScoreModel,
                                                           IsotonicCalibrator, float]:
    model = CatBoostScoreModel(threads=threads)
    model.load(directory)
    calibrator = IsotonicCalibrator()
    calibrator.load(directory / CALIBRATOR_FILE)
    payload = json.loads((directory / THRESHOLD_FILE).read_text(encoding="utf-8"))
    return model, calibrator, float(payload["threshold"])


def has_ranker(directory: Path) -> bool:
    return all((directory / f).exists() for f in (MODEL_FILE, CALIBRATOR_FILE, THRESHOLD_FILE))


def save_fusion(model: FusionModel, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"rules": model.rules.to_json(), "threshold": model.threshold}
    (directory / RULES_FILE).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    for source, calibrator in model.calibrators.items():
        if isinstance(calibrator, IsotonicCalibrator):
            calibrator.save(directory / f"{source}.json")


def load_fusion(directory: Path) -> FusionModel:
    payload = json.loads((directory / RULES_FILE).read_text(encoding="utf-8"))
    calibrators: dict[str, Calibrator] = {}
    for source in SOURCES:
        calibrator = IsotonicCalibrator()
        calibrator.load(directory / f"{source}.json")
        calibrators[source] = calibrator
    return FusionModel(FusionRules.from_json(payload["rules"]), calibrators,
                       float(payload["threshold"]), [])


def has_fusion(directory: Path) -> bool:
    return (directory / RULES_FILE).exists() and all(
        (directory / f"{s}.json").exists() for s in SOURCES)
