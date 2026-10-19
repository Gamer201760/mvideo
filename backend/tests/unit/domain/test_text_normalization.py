import pytest

from app.domain.card_text import SellerParam, build_card_text, match_form
from app.domain.extractors import extract_candidates
from app.domain.values import canonical_text
from app.usecase.lexicon_builder import TrainValue, build_lexicon


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ＳＡＭＳＵＮＧ １２８ＧＢ", "samsung 128gb"),
        ("Ёлка\u2007Black\u3000１２", "елка black 12"),
        ("١٢٨ GB", "128 gb"),
        ("İ Ⅳ ² ﬀ", "İ ⅳ ² ﬀ"),
    ],
)
def test_matching_form_normalizes_safe_characters_without_moving_offsets(
    text: str,
    expected: str,
) -> None:
    assert match_form(text) == expected
    assert len(match_form(text)) == len(text)


def test_normalized_brand_keeps_original_quote() -> None:
    lexicon = build_lexicon([TrainValue(1, "Бренд", "Samsung", None)] * 3)
    card = build_card_text("Телефон ＳＡＭＳＵＮＧ", "", ())
    found = extract_candidates(card, lexicon.profiles, lexicon, 1)
    assert found and found[0].value == "Samsung"
    assert card.text[found[0].start : found[0].end] == found[0].evidence == "ＳＡＭＳＵＮＧ"


@pytest.mark.parametrize("text", ["Samsng", "Sаmsung", "SM-S921B", "SM-S926B"])
def test_normalization_does_not_guess_brands_or_model_identifiers(text: str) -> None:
    assert canonical_text(text) == text.lower()


@pytest.mark.parametrize(
    ("attribute", "unit", "raw", "expected"),
    [
        ("Вес", "кг", "５００ г", "0.5 кг"),
        ("Вес", "кг", "1\u202f000 г", "1 кг"),
        ("Вес", "кг", "2 кg", "2 кг"),
        ("Длина", "мм", "2 сm", "20 мм"),
        ("Память", "гб", "１２８ ГB", "128 гб"),
        ("Емкость аккумулятора", "мАч", "5 000 мAч", "5000 мач"),
    ],
)
@pytest.mark.parametrize("seller", [False, True])
def test_quantity_normalization_handles_spacing_unicode_and_mixed_unit_letters(
    attribute: str,
    unit: str,
    raw: str,
    expected: str,
    seller: bool,
) -> None:
    lexicon = build_lexicon([TrainValue(1, attribute, "1", unit)] * 3)
    description = "" if seller else f"{attribute}： {raw}"
    params = (SellerParam(attribute, raw),) if seller else ()
    card = build_card_text("Товар", description, params)
    found = extract_candidates(card, lexicon.profiles, lexicon, 1)
    assert found and {c.value for c in found} == {expected}
    assert all(card.text[c.start : c.end] == c.evidence for c in found)
    expected_quote = raw if seller else raw.replace("\u202f", " ")
    assert any(c.evidence == expected_quote for c in found)
