from collections.abc import Iterator, Mapping, Sequence

from app.domain.card_text import SellerParam
from app.usecase.baseline_ports import (
    CandidateRow,
    CardPrediction,
    CardRecord,
    GoldRecord,
    RequiredRecord,
)
from app.usecase.lexicon_builder import TrainValue
from app.usecase.ranker import RankerConfig, RunRanker
from app.usecase.ranker_ports import FeatureTable

PHONE = 761

GOLD = {
    4: [GoldRecord("Бренд", "Samsung", None), GoldRecord("Цвет", "черный", None)],
    8: [GoldRecord("Бренд", "Xiaomi", None), GoldRecord("Цвет", "белый", None)],
    1: [GoldRecord("Бренд", "Samsung", None), GoldRecord("Цвет", "черный", None)],
    2: [GoldRecord("Бренд", "Samsung", None), GoldRecord("Цвет", "белый", None)],
    3: [GoldRecord("Бренд", "Xiaomi", None)],
}
CARDS = {
    "train": [
        CardRecord(4, PHONE, "М.Видео", "Смартфон Samsung черный", "", (), "train"),
        CardRecord(8, PHONE, "ИП", "Смартфон Xiaomi белый", "корпус черный", (), "train"),
    ],
    "val": [CardRecord(3, PHONE, "ИП", "Смартфон Xiaomi", "", (), "val")],
    "test": [
        CardRecord(1, PHONE, "М.Видео", "Смартфон Samsung черный", "", (), "test"),
        CardRecord(2, PHONE, "ИП", "Смартфон Samsung", "", (SellerParam("Цвет", "белый"),),
                   "test"),
    ],
}


class MemorySink:
    def __init__(self) -> None:
        self.predictions: list[CardPrediction] = []
        self.closed = False

    def write(self, predictions: Sequence[CardPrediction], candidates: Sequence[CandidateRow]) -> None:
        self.predictions.extend(predictions)

    def close(self) -> None:
        self.closed = True


class MemoryReports:
    def __init__(self) -> None:
        self.markdown = ""

    def write(self, report: Mapping[str, object], markdown: str) -> None:
        self.markdown = markdown


class SilentLogger:
    def info(self, event: str, **fields: object) -> None: ...

    def warning(self, event: str, **fields: object) -> None: ...

    def error(self, event: str, *, exc: BaseException | None = None, **fields: object) -> None: ...


class FakeRankerSource:
    def train_values(self, attributes: frozenset[str]) -> Iterator[TrainValue]:
        for _ in range(3):
            yield TrainValue(PHONE, "Бренд", "Samsung", None)
            yield TrainValue(PHONE, "Бренд", "Xiaomi", None)
            yield TrainValue(PHONE, "Цвет", "черный", None)
            yield TrainValue(PHONE, "Цвет", "белый", None)

    def required(self) -> Sequence[RequiredRecord]:
        return [RequiredRecord(PHONE, "Бренд", 10.0), RequiredRecord(PHONE, "Цвет", 2.0)]

    def category_stats(self) -> Mapping[int, tuple[int, int]]:
        return {PHONE: (100, 2)}

    def seller_cards(self) -> Mapping[str, int]:
        return {"М.Видео": 5000}

    def gold(self, splits: frozenset[str]) -> Mapping[int, Sequence[GoldRecord]]:
        return self.gold_where(splits, frozenset({"Бренд", "Цвет"}), 1)

    def gold_where(
        self, splits: frozenset[str], attributes: frozenset[str], modulo: int
    ) -> Mapping[int, Sequence[GoldRecord]]:
        wanted = {c.sku_id for s in splits for c in CARDS.get(s, []) if c.sku_id % modulo == 0}
        return {sku: [g for g in gold if g.attribute in attributes]
                for sku, gold in GOLD.items() if sku in wanted}

    def cards(self, splits: frozenset[str] | None, batch: int) -> Iterator[list[CardRecord]]:
        yield [c for s in sorted(splits or CARDS) for c in CARDS.get(s, [])]


class HeuristicModel:
    def __init__(self) -> None:
        self.rows = 0

    def fit(self, train: FeatureTable, names: Sequence[str], categorical: Sequence[str]) -> None:
        self.rows = train.rows
        self.width = train.width

    def predict(self, table: FeatureTable) -> Sequence[float]:
        return [min(1.0, table.numeric[i * table.width]) for i in range(table.rows)]

    def importances(self) -> Mapping[str, float]:
        return {"heuristic": 1.0}


class IdentityCalibrator:
    def fit(self, scores: Sequence[float], labels: Sequence[bool]) -> None:
        self.fitted = len(scores)

    def transform(self, scores: Sequence[float]) -> Sequence[float]:
        return [max(0.0, min(1.0, s)) for s in scores]


def test_ranker_trains_tunes_evaluates_and_reports() -> None:
    model, calibrator = HeuristicModel(), IdentityCalibrator()
    sink, reports = MemorySink(), MemoryReports()
    usecase = RunRanker(FakeRankerSource(), model, calibrator, sink, reports, SilentLogger())
    report = usecase.run(RankerConfig())
    assert model.rows > 0 and calibrator.fitted > 0
    assert sink.closed and [p.sku_id for p in sink.predictions] == [1, 2]
    first = {v.attribute: v for v in sink.predictions[0].values}
    assert first["Бренд"].value == "Samsung" and first["Бренд"].evidence == "Samsung"
    assert report["confidence_calibrated"] is True
    threshold = report["threshold"]
    assert isinstance(threshold, dict) and 0 < threshold["value"] < 1
    calibration = report["calibration"]
    assert isinstance(calibration, dict) and calibration["calibrated"]["picks"] > 0
    assert "Абляция" in reports.markdown and "Калибровка" in reports.markdown


def test_ranker_skips_train_cards_outside_the_modulo_sample() -> None:
    model = HeuristicModel()
    usecase = RunRanker(FakeRankerSource(), model, IdentityCalibrator(), MemorySink(),
                        MemoryReports(), SilentLogger())
    usecase.run(RankerConfig(train_modulo=8))
    sampled = HeuristicModel()
    RunRanker(FakeRankerSource(), sampled, IdentityCalibrator(), MemorySink(), MemoryReports(),
              SilentLogger()).run(RankerConfig(train_modulo=4))
    assert 0 < model.rows < sampled.rows


class CapturingModel(HeuristicModel):
    def fit(self, train: FeatureTable, names: Sequence[str], categorical: Sequence[str]) -> None:
        super().fit(train, names, categorical)
        self.columns = {name: [train.numeric[r * train.width + i] for r in range(train.rows)]
                        for i, name in enumerate(names)}


def test_blind_cards_train_without_category_priors() -> None:
    seen, blind = CapturingModel(), CapturingModel()
    for model, remainder in ((seen, 3), (blind, 0)):
        RunRanker(FakeRankerSource(), model, IdentityCalibrator(), MemorySink(), MemoryReports(),
                  SilentLogger()).run(RankerConfig(blind_modulo=4, blind_remainder=remainder))
    assert max(seen.columns["prior_known"]) == 1.0 and max(seen.columns["prior_max"]) > 0
    assert max(blind.columns["prior_known"]) == 0.0 and max(blind.columns["prior_max"]) == 0.0
