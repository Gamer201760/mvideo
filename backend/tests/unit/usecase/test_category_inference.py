from collections.abc import Iterator, Mapping, Sequence

from app.domain.category_guess import CategoryGuess, CategorySource, Ranked
from app.usecase.category_inference import CategoryConfig, InferCategories
from app.usecase.category_ports import CategoryCard, ClickVote
from app.usecase.interface import LogValue

PHONES, LAPTOPS = 761, 987


def card(sku: int, category: int | None, split: str | None, text: str) -> CategoryCard:
    return CategoryCard(sku, category, split, text)


CARDS = [
    *(card(i, PHONES, "train", "смартфон samsung") for i in range(1, 6)),
    *(card(i, LAPTOPS, "train", "ноутбук lenovo") for i in range(6, 11)),
    card(11, PHONES, "val", "смартфон xiaomi"),
    card(12, LAPTOPS, "val", "ноутбук asus"),
    card(15, LAPTOPS, "val", "непонятное"),
    card(16, 555, "new_category", "непонятная швейная машина"),
    card(13, PHONES, "test", "смартфон apple"),
    card(14, LAPTOPS, "test", "ноутбук hp"),
    card(20, None, None, "смартфон honor"),
    card(21, None, None, "что-то непонятное"),
    card(22, None, None, "ноутбук без кликов"),
]


class FakeCorpus:
    def required_categories(self) -> frozenset[int]:
        return frozenset({PHONES, LAPTOPS})

    def category_names(self) -> Mapping[int, str]:
        return {PHONES: "Смартфоны", LAPTOPS: "Ноутбуки"}

    def labelled(self, splits: frozenset[str]) -> Iterator[CategoryCard]:
        return (c for c in CARDS if c.catalog_category is not None and c.split in splits)

    def click_votes(self) -> Iterator[ClickVote]:
        yield ClickVote(1, 5000, 10)
        yield ClickVote(13, 5000, 3)
        yield ClickVote(22, 5000, 7)

    def cards(self, batch: int) -> Iterator[list[CategoryCard]]:
        for start in range(0, len(CARDS), batch):
            yield CARDS[start:start + batch]


class KeywordClassifier:
    def __init__(self) -> None:
        self.fitted = 0

    def fit(self, texts: Sequence[str], labels: Sequence[int]) -> None:
        self.fitted = len(texts)

    def rank(self, texts: Sequence[str], k: int) -> list[Ranked]:
        result: list[Ranked] = []
        for text in texts:
            if "смартфон" in text:
                result.append([(PHONES, 0.9), (LAPTOPS, 0.1)])
            elif "ноутбук" in text:
                result.append([(LAPTOPS, 0.8), (PHONES, 0.2)])
            else:
                result.append([(PHONES, 0.3), (LAPTOPS, 0.3)])
        return result[:] if k else []


class MemorySink:
    def __init__(self) -> None:
        self.guesses: list[CategoryGuess] = []
        self.closed = False
        self.reports: list[Mapping[str, object]] = []

    def write(self, guesses: Sequence[CategoryGuess]) -> None:
        self.guesses.extend(guesses)

    def close(self) -> None:
        self.closed = True

    def report(self, report: Mapping[str, object], markdown: str) -> None:
        assert "Категории" in markdown
        self.reports.append(report)


class SilentLogger:
    def info(self, event: str, **fields: LogValue) -> None: ...

    def warning(self, event: str, **fields: LogValue) -> None: ...

    def error(self, event: str, *, exc: BaseException | None = None, **fields: LogValue) -> None: ...


def test_infer_categories_end_to_end() -> None:
    classifier = KeywordClassifier()
    sink = MemorySink()
    report = InferCategories(FakeCorpus(), classifier, sink, SilentLogger()).run(
        CategoryConfig(target_precision=0.9, batch=4))
    assert classifier.fitted == 10
    assert sink.closed
    by_sku = {g.sku_id: g for g in sink.guesses}
    assert by_sku[1].source is CategorySource.CATALOG
    assert by_sku[22].source is CategorySource.CLICKS and by_sku[22].category_id == PHONES
    assert by_sku[20].source is CategorySource.CLASSIFIER and by_sku[20].category_id == PHONES
    assert 21 not in by_sku
    assert report["threshold"] == 0.31
    selection = report["threshold_selection"]
    assert isinstance(selection, dict)
    assert selection["by_new_category_rejection"] == 0.31
    assert selection["new_category_rejected"] == 1.0
    test = report["classifier_test"]
    assert isinstance(test, dict) and test["top1"] == 1.0
    clicks = report["clicks"]
    assert isinstance(clicks, dict) and clicks["test_accuracy"] == 1.0
    coverage = report["coverage"]
    assert isinstance(coverage, dict) and coverage["with_category"] == 18
    assert coverage["outside_catalog_without_clicks"] == 2
    assert coverage["classifier_accepted"] == 1
    samples = coverage["samples"]
    assert isinstance(samples, list) and len(samples) == 2
    assert sink.reports == [report]
