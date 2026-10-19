import pytest
from tests.unit.domain.evidence_cases import extract


@pytest.mark.parametrize("separator", ["-", "–", "—"])
def test_field_separator_is_not_a_negative_sign(separator: str) -> None:
    quote = f"ширина одного полотна {separator} 137 см"
    text = f"Шторы\n{quote}"
    _, result = extract(text, "Ширина одного полотна", "numeric", "137", "см", quote)
    assert len(result.items) == 1
    answer = result.items[0]
    assert text[answer.start : answer.end] == answer.quote == quote
    assert answer.normalized_value == "137"
    assert not result.rejections


@pytest.mark.parametrize("quote", ["Товар Nordwell", "Nordwell"])
def test_later_colon_does_not_relabel_earlier_evidence(quote: str) -> None:
    text = "Товар Nordwell Узор: волны\nОписание товара"
    _, result = extract(text, "Бренд", "free", "Nordwell", "", quote)
    assert len(result.items) == 1
    answer = result.items[0]
    assert text[answer.start : answer.end] == answer.quote == quote
    assert not result.rejections


@pytest.mark.parametrize(
    ("text", "attribute", "value", "unit", "quote"),
    [
        ("Температура: -7 °с", "Температура", "7", "°с", "-7 °с"),
        ("Температура: − 7 °с", "Температура", "7", "°с", "− 7 °с"),
        ("Вес: - 7 кг", "Вес", "7", "кг", "- 7 кг"),
        ("Вес -7 кг", "Вес", "7", "кг", "Вес -7 кг"),
        ("Вес - 7–9 кг", "Вес", "7", "кг", "Вес - 7–9 кг"),
        ("Вес - 7 л", "Вес", "7", "кг", "Вес - 7 л"),
        ("Нагрузка - 7 кг", "Вес", "7", "кг", "Нагрузка - 7 кг"),
    ],
)
def test_numeric_separator_fix_preserves_rejections(
    text: str, attribute: str, value: str, unit: str, quote: str
) -> None:
    _, result = extract(text, attribute, "numeric", value, unit, quote)
    assert not result.items
    assert result.rejections


def test_colon_still_binds_a_value_to_its_named_field() -> None:
    text = "Товар\nМодель: Nordwell"
    _, result = extract(text, "Бренд", "free", "Nordwell", "", "Nordwell")
    assert not result.items
    assert result.rejections[0].reason == "field_mismatch"
