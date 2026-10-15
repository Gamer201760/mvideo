from collections.abc import Iterator, Mapping, Sequence

from app.domain.card_text import SellerParam
from app.usecase.baseline import BaselineConfig, RunBaseline
from app.usecase.baseline_ports import (
    CandidateRow,
    CardPrediction,
    CardRecord,
    GoldRecord,
    RequiredRecord,
)
from app.usecase.lexicon_builder import TrainValue

PHONE = 761


class FakeSource:
    def train_values(self, attributes: frozenset[str]) -> Iterator[TrainValue]:
        for _ in range(3):
            yield TrainValue(PHONE, "Бренд", "Samsung", None)
            yield TrainValue(PHONE, "Цвет", "черный", None)
            yield TrainValue(PHONE, "Емкость аккумулятора", "5000", "мАч")

    def required(self) -> Sequence[RequiredRecord]:
        return [RequiredRecord(PHONE, "Бренд", 10.0), RequiredRecord(PHONE, "Цвет", 2.0)]

    def category_stats(self) -> Mapping[int, tuple[int, int]]:
        return {PHONE: (100, 2)}

    def seller_cards(self) -> Mapping[str, int]:
        return {"М.Видео": 5000}

    def gold(self, splits: frozenset[str]) -> Mapping[int, Sequence[GoldRecord]]:
        return {
            1: [GoldRecord("Бренд", "Samsung", None), GoldRecord("Цвет", "черный", None),
                GoldRecord("Емкость аккумулятора", "5000", "мАч")],
            2: [GoldRecord("Бренд", "Samsung", None), GoldRecord("Цвет", "белый", None)],
        }

    def cards(self, splits: frozenset[str] | None, batch: int) -> Iterator[list[CardRecord]]:
        yield [
            CardRecord(1, PHONE, "М.Видео", "Смартфон Samsung черный", "Батарея 5000 мАч", (),
                       "test"),
            CardRecord(2, PHONE, "ИП", "Смартфон Samsung", "",
                       (SellerParam("Цвет", "черный"),), "test"),
        ]


class MemorySink:
    def __init__(self) -> None:
        self.predictions: list[CardPrediction] = []
        self.candidates: list[CandidateRow] = []
        self.closed = False

    def write(self, predictions: Sequence[CardPrediction], candidates: Sequence[CandidateRow]) -> None:
        self.predictions.extend(predictions)
        self.candidates.extend(candidates)

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


def test_baseline_predicts_evaluates_and_reports() -> None:
    sink, reports = MemorySink(), MemoryReports()
    report = RunBaseline(FakeSource(), sink, reports, SilentLogger()).run(BaselineConfig())
    assert sink.closed and len(sink.predictions) == 2
    first = {v.attribute: v for v in sink.predictions[0].values}
    assert first["Бренд"].value == "Samsung" and first["Бренд"].evidence == "Samsung"
    assert first["Емкость аккумулятора"].value.startswith("5000")
    groups = report["groups"]
    assert isinstance(groups, dict)
    micro = groups["all"]["micro"]
    assert micro["gold"] == 5
    assert micro["precision"] == 0.8
    assert micro["pairs"] == 6
    assert micro["coverage_before"] == round(1 / 6, 4)
    assert "category:smartphones" in groups
    assert "Сводка по срезам" in reports.markdown
    assert all(c.evidence for c in sink.candidates)
