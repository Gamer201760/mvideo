from collections import Counter

import pytest

from app.domain.card_text import build_card_text, clean_text
from app.domain.profile import Kind, profile_attribute
from app.domain.values import canonical_key, canonical_text, leading_quantity


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("алый", "красный"), ("Red", "красный"), ("Чёрная", "черный"), ("black", "черный")],
)
def test_color_forms_collapse_to_base(raw: str, expected: str) -> None:
    assert canonical_text(raw) == expected


def test_memory_units_normalize() -> None:
    assert canonical_key("256Гб", None, True) == canonical_key("256 ГБ", None, True) == "256"
    quantity = leading_quantity("256GB")
    assert quantity is not None and quantity.unit == "гб"


def test_diagonal_with_comma_and_inch_mark() -> None:
    quantity = leading_quantity('6,7"')
    assert quantity is not None
    assert (quantity.number, quantity.unit) == (6.7, '"')
    assert canonical_key('6,7"', None, True) == canonical_key("6.70", '"', True) == "6.7"


def test_non_unit_suffix_is_not_quantity() -> None:
    assert leading_quantity("2 nano-SIM") is None


def test_clean_text_strips_html_and_keeps_lines() -> None:
    assert clean_text("<p>Цвет:&nbsp;красный</p><br>Вес: 2 кг") == "Цвет: красный\nВес: 2 кг"


def test_card_text_zones() -> None:
    card = build_card_text("Смартфон X", "<b>Описание</b>", ())
    assert card.zone(0) == "title"
    assert card.zone(card.text.index("Описание")) == "description"


def test_profile_detects_kinds() -> None:
    numeric: Counter[tuple[str, str | None]] = Counter({("6.7", '"'): 5, ("6.1", '"'): 3})
    boolean: Counter[tuple[str, str | None]] = Counter({("Да", None): 5, ("Нет", None): 5})
    colors: Counter[tuple[str, str | None]] = Counter({("черный", None): 5, ("белый", None): 3})
    assert profile_attribute("Диагональ", numeric).kind is Kind.NUMERIC
    assert profile_attribute("Диагональ", numeric).unit == '"'
    assert profile_attribute("NFC", boolean).kind is Kind.BOOLEAN
    assert profile_attribute("Цвет", colors).kind is Kind.CATEGORICAL
