from collections.abc import Iterator, Sequence
from datetime import UTC, datetime

from test_twins import FakeIndex, Identity

from app.adapter.dataset.stand_pack_file import decode, encode
from app.domain.card_text import build_card_text
from app.domain.lexicon import Lexicon
from app.domain.twin import TWIN_SOURCE, twin_title
from app.usecase.baseline_ports import CardRecord, RequiredRecord
from app.usecase.extraction import CardExtraction
from app.usecase.stand_ports import StandPack, StandTwin
from app.usecase.stand_twin_pack import build_stand_twins
from app.usecase.stand_twins import StandTwins, TwinSettings

TITLE = "Смартфон Samsung Galaxy A55 8/256GB"
TWIN = StandTwin(sku_id=10, title=twin_title(TITLE), brand="samsung", model="a55",
                 values={"Вес": ("190", "190 г"), "Бренд": ("samsung", "Samsung")})


def _extraction(title: str) -> CardExtraction:
    return CardExtraction(build_card_text(title, "Отличный смартфон", ()), {}, (), {}, {})


def test_pack_keeps_twins_through_file_format() -> None:
    pack = StandPack(built_at=datetime(2026, 10, 15, tzinfo=UTC).isoformat(), threshold=0.35,
                     profiles={}, entries=[], priors={}, required=[], categories=[], examples=[],
                     twins=[TWIN])
    restored = decode(encode(pack))
    assert list(restored.twins) == [TWIN]


def test_twin_fills_open_slot_with_sku_evidence() -> None:
    twins = StandTwins([TWIN], FakeIndex(), Identity(), TwinSettings(threshold=0.55))
    picks = twins.picks(_extraction(TITLE), ["Вес", "Цвет"], None)
    assert set(picks) == {"Вес"}
    pick = picks["Вес"]
    assert pick.candidate.key == "190" and pick.candidate.value == "190 г"
    assert pick.candidate.source == TWIN_SOURCE and pick.candidate.start == -1
    assert pick.candidate.evidence.startswith("SKU 10")


def test_no_twin_below_threshold_or_with_other_numbers() -> None:
    strict = StandTwins([TWIN], FakeIndex(), Identity(), TwinSettings(threshold=1.01))
    assert strict.picks(_extraction(TITLE), ["Вес"], None) == {}
    loose = StandTwins([TWIN], FakeIndex(), Identity(), TwinSettings(threshold=0.1))
    other = "Смартфон Samsung Galaxy A55 8/128GB"
    assert loose.picks(_extraction(other), ["Вес"], None) == {}


class Rows:
    def cards(self, splits: frozenset[str] | None, batch: int) -> Iterator[list[CardRecord]]:
        yield [CardRecord(10, 761, "ИП", TITLE, "", (), "train"),
               CardRecord(11, 761, "ИП", "Смартфон Samsung Galaxy A35 8/128GB", "", (), "train"),
               CardRecord(12, 999, "ИП", "Чайник Bosch", "", (), "train")]

    def gold_rows(
        self, splits: frozenset[str], attributes: frozenset[str]
    ) -> Iterator[Sequence[tuple[int, str, str, str | None]]]:
        yield [(10, "Бренд", "Samsung", None), (10, "Вес", "190", "г"),
               (10, "Гарантия", "1 год", None), (11, "Бренд", "Samsung", None),
               (12, "Бренд", "Bosch", None)]


def test_pack_twins_cap_categories_and_attributes() -> None:
    required = [RequiredRecord(761, "Вес", 1.0)]
    twins = build_stand_twins(Rows(), Lexicon({}, [], {}), required, frozenset({761}),
                              per_category=1)
    assert [t.sku_id for t in twins] == [10]
    assert set(twins[0].values) == {"Бренд", "Вес"}
    assert twins[0].brand == "samsung"
