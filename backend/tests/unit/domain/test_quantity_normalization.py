import pytest

from app.domain.card_text import SellerParam, build_card_text
from app.domain.extractors import extract_candidates
from app.domain.values import canonical_key
from app.usecase.lexicon_builder import TrainValue, build_lexicon


def test_numeric_keys_distinguish_units_and_match_equivalent_quantities() -> None:
    assert canonical_key("1 г", None, True) != canonical_key("1 кг", None, True)
    assert canonical_key("1000 г", None, True) == canonical_key("1 кг", None, True)
    assert canonical_key("1 кг", None, True) != canonical_key("1 л", None, True)


@pytest.mark.parametrize("zone", ["description", "seller"])
@pytest.mark.parametrize(
    ("attribute", "unit", "raw", "expected"),
    [
        ("Вес", "кг", "500 г", "0.5 кг"),
        ("Вес", "г", "0.5 кг", "500 г"),
        ("Длина", "мм", "2.5 см", "25 мм"),
        ("Мощность", "вт", "1.5 кВт", "1500 вт"),
        ("Частота", "мгц", "2 ГГц", "2000 мгц"),
    ],
)
def test_extraction_converts_to_catalog_unit_and_keeps_quote(
    zone: str,
    attribute: str,
    unit: str,
    raw: str,
    expected: str,
) -> None:
    lexicon = build_lexicon([TrainValue(1, attribute, "1", unit)] * 3)
    description = f"{attribute}: {raw}" if zone == "description" else ""
    params = (SellerParam(attribute, raw),) if zone == "seller" else ()
    card = build_card_text("Товар", description, params)

    candidates = extract_candidates(card, lexicon.profiles, lexicon, 1)

    assert candidates
    assert {c.value for c in candidates} == {expected}
    assert all(card.text[c.start : c.end] == c.evidence == raw for c in candidates)


def test_incompatible_unit_is_not_relabelled_as_weight() -> None:
    lexicon = build_lexicon([TrainValue(1, "Вес", "1", "кг")] * 3)
    card = build_card_text("Товар", "Вес: 500 л", (SellerParam("Вес", "500 Вт"),))
    assert extract_candidates(card, lexicon.profiles, lexicon, 1) == []


@pytest.mark.parametrize("raw", ["400 - 600 г", "400-600 г", "от 400 до 600 г"])
def test_seller_range_is_compared_in_catalog_units(raw: str) -> None:
    lexicon = build_lexicon([TrainValue(1, "Вес", "1", "кг")] * 3)
    card = build_card_text("Товар", "Вес 0.5 кг", (SellerParam("Вес", raw),))
    found = extract_candidates(card, lexicon.profiles, lexicon, 1)
    assert found and all(c.seller_fit == 1 for c in found)


@pytest.mark.parametrize("raw", ["500 неизвестно", "500 кг/м", "500 м²"])
def test_unsupported_units_do_not_become_weight(raw: str) -> None:
    lexicon = build_lexicon([TrainValue(1, "Вес", "1", "кг")] * 3)
    card = build_card_text("Товар", "", (SellerParam("Вес", raw),))
    assert extract_candidates(card, lexicon.profiles, lexicon, 1) == []
