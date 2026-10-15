from collections.abc import Iterator, Mapping, Sequence

from app.domain.twin import twin_title
from app.usecase.baseline_ports import CardRecord, GoldRecord, RequiredRecord
from app.usecase.lexicon_builder import TrainValue
from app.usecase.twin_ports import StageRecord, StageValue, TwinPrediction
from app.usecase.twins import RunTwins, TwinConfig

PHONE = 761
ATTRS = ("Бренд", "Цвет", "Вес")
GOLD = {
    10: [GoldRecord("Бренд", "Samsung", None), GoldRecord("Вес", "190", "г"),
         GoldRecord("Модель", "A55", None)],
    11: [GoldRecord("Бренд", "Xiaomi", None), GoldRecord("Вес", "205", "г"),
         GoldRecord("Модель", "Note 13", None)],
    20: [GoldRecord("Бренд", "Samsung", None), GoldRecord("Вес", "190", "г"),
         GoldRecord("Модель", "A55", None)],
    30: [GoldRecord("Бренд", "Samsung", None), GoldRecord("Вес", "190", "г")],
    31: [GoldRecord("Бренд", "Xiaomi", None), GoldRecord("Вес", "999", "г")],
}
CARDS = {
    "train": [CardRecord(10, PHONE, "ИП", "Смартфон Samsung Galaxy A55 8/256GB", "", (), "train"),
              CardRecord(11, PHONE, "ИП", "Смартфон Xiaomi Redmi Note 13 8/256GB", "", (),
                         "train")],
    "val": [CardRecord(20, PHONE, "ИП", "Смартфон Samsung Galaxy A55 8/256GB", "", (), "val")],
    "test": [CardRecord(30, PHONE, "ИП", "Смартфон Samsung Galaxy A55 8/256GB", "", (), "test")],
    "new_category": [CardRecord(31, PHONE, "ИП", "Смартфон Xiaomi Redmi Note 13 8/512GB", "", (),
                                "new_category")],
}


class FakeSource:
    def train_values(self, attributes: frozenset[str]) -> Iterator[TrainValue]:
        for _ in range(3):
            yield TrainValue(PHONE, "Бренд", "Samsung", None)
            yield TrainValue(PHONE, "Бренд", "Xiaomi", None)
            yield TrainValue(PHONE, "Вес", "190", "г")
            yield TrainValue(PHONE, "Вес", "205", "г")

    def required(self) -> Sequence[RequiredRecord]:
        return [RequiredRecord(PHONE, a, 1.0) for a in ATTRS]

    def category_stats(self) -> Mapping[int, tuple[int, int]]:
        return {PHONE: (100, 2)}

    def seller_cards(self) -> Mapping[str, int]:
        return {"ИП": 10}

    def gold(self, splits: frozenset[str]) -> Mapping[int, Sequence[GoldRecord]]:
        return self.gold_where(splits, frozenset(ATTRS), 1)

    def gold_where(
        self, splits: frozenset[str], attributes: frozenset[str], modulo: int
    ) -> Mapping[int, Sequence[GoldRecord]]:
        wanted = {c.sku_id for s in splits for c in CARDS.get(s, [])}
        return {sku: [g for g in gold if g.attribute in attributes]
                for sku, gold in GOLD.items() if sku in wanted}

    def cards(self, splits: frozenset[str] | None, batch: int) -> Iterator[list[CardRecord]]:
        chosen = [c for s, cards in CARDS.items() if splits is None or s in splits for c in cards]
        if chosen:
            yield chosen

    def gold_rows(
        self, splits: frozenset[str], attributes: frozenset[str]
    ) -> Iterator[Sequence[tuple[int, str, str, str | None]]]:
        for sku, gold in self.gold_where(splits, attributes, 1).items():
            yield [(sku, g.attribute, g.value, g.unit) for g in gold]

    def stage_records(self, name: str) -> Mapping[int, StageRecord]:
        brand = StageValue("Samsung", 0.9, "title_model", ("title_model",), 9, 16)
        return {30: StageRecord({"sku_id": 30, "attributes": {}, "review": {}}, {"Бренд": brand})}


class FakeIndex:
    def __init__(self) -> None:
        self.fitted: list[str] = []

    def fit(self, titles: Sequence[str]) -> None:
        self.fitted = list(titles)

    def neighbors(self, titles: Sequence[str], k: int) -> list[list[tuple[int, float]]]:
        result = []
        for title in titles:
            words = set(title.split())
            scored = [(i, len(words & set(t.split())) / len(words | set(t.split())))
                      for i, t in enumerate(self.fitted)]
            result.append(sorted(scored, key=lambda x: -x[1])[:k])
        return result


class Identity:
    def fit(self, scores: Sequence[float], labels: Sequence[bool]) -> None: ...

    def transform(self, scores: Sequence[float]) -> Sequence[float]:
        return list(scores)


class MemorySink:
    def __init__(self) -> None:
        self.predictions: list[TwinPrediction] = []

    def write(self, predictions: Sequence[TwinPrediction]) -> None:
        self.predictions.extend(predictions)

    def close(self) -> None: ...


class MemoryReports:
    def __init__(self) -> None:
        self.markdown = ""

    def write(self, report: Mapping[str, object], markdown: str) -> None:
        self.markdown = markdown


class SilentLogger:
    def info(self, event: str, **fields: object) -> None: ...

    def warning(self, event: str, **fields: object) -> None: ...

    def error(self, event: str, *, exc: BaseException | None = None, **fields: object) -> None: ...


def run() -> tuple[FakeIndex, MemorySink, Mapping[str, object], str]:
    index, sink, reports = FakeIndex(), MemorySink(), MemoryReports()
    report = RunTwins(FakeSource(), index, Identity(), sink, reports, SilentLogger()).run(
        TwinConfig(k=5))
    return index, sink, report, reports.markdown


def test_index_holds_only_train_cards() -> None:
    index, _, _, _ = run()
    train = {twin_title(c.title) for c in CARDS["train"]}
    held_out = {twin_title(c.title) for s in ("val", "test", "new_category") for c in CARDS[s]}
    assert set(index.fitted) == train
    assert len(index.fitted) == len(CARDS["train"])
    assert held_out - train


def test_twin_fills_open_slot_and_skips_mismatched_numbers() -> None:
    _, sink, report, markdown = run()
    by_sku = {p.stage["sku_id"]: p for p in sink.predictions}
    transfer, _ = by_sku[30].transfers["Вес"]
    assert transfer.twin_sku == 10
    assert transfer.key == "190"
    assert "Бренд" not in by_sku[30].transfers
    assert by_sku[31].transfers == {}
    assert report["threshold"] in TwinConfig().grid
    assert "двойники" in markdown
