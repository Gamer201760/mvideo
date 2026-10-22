import pytest
from tests.unit.domain.evidence_cases import extract

from app.domain.acceptance import AcceptancePolicy
from app.domain.evidence_risk import assess_extraction


@pytest.mark.parametrize(
    "qualifier",
    [
        "примерно",
        "приблизительно",
        "ориентировочно",
        "порядка",
        "около",
        "почти",
        "максимум",
        "минимум",
        "как минимум",
        "не более чем",
        "больше",
        "меньше",
        "~",
        "≈",
        "≤",
        "≥",
        "<",
        ">",
        "не больше",
        "не меньше чем",
        "менее чем",
        "больше чем",
        "не превышает",
        "не выше",
        "в среднем",
    ],
)
@pytest.mark.parametrize("short_quote", [False, True])
def test_numeric_qualifier_cannot_become_exact(qualifier: str, short_quote: bool) -> None:
    text = f"Мощность: {qualifier} 100 Вт"
    _, result = extract(text, "Мощность", "numeric", "100", "Вт", "100 Вт" if short_quote else text)
    assert not result.items
    assert result.review and result.rejections


@pytest.mark.parametrize("qualifier", ["примерно", "максимум", "минимум", "приблизительно"])
def test_postfix_qualifier_cannot_become_exact(qualifier: str) -> None:
    _, result = extract(
        f"Мощность: 100 Вт {qualifier}", "Мощность", "numeric", "100", "Вт", "100 Вт"
    )
    assert not result.items
    assert result.rejections


@pytest.mark.parametrize(
    ("evidence", "value"),
    [
        ("максимум 100 Вт", "до 100"),
        ("как минимум 100 Вт", "не менее 100"),
        ("не более чем 100 Вт", "до 100"),
        ("≤ 100 Вт", "до 100"),
        ("примерно 100 Вт", "примерно 100"),
        ("приблизительно 100 Вт", "приблизительно 100"),
        ("от 50 до 100 Вт", "50–100"),
    ],
)
def test_supported_numeric_bounds_preserve_meaning(evidence: str, value: str) -> None:
    card, result = extract(f"Мощность: {evidence}", "Мощность", "numeric", value, "Вт", evidence)
    assert len(result.items) == 1, result.validation_errors
    answer = result.items[0]
    assert answer.normalized_value == value
    assert card.text[answer.start : answer.end] == answer.quote == evidence


@pytest.mark.parametrize(
    "description",
    [
        "возможно красный",
        "вероятно красный",
        "предположительно красный",
        "может быть красный",
        "красный или синий",
        "красный либо синий",
    ],
)
@pytest.mark.parametrize("short_quote", [False, True])
def test_uncertain_color_is_rejected_even_with_literal_quote(
    description: str, short_quote: bool
) -> None:
    text = f"Цвет: {description}"
    _, result = extract(
        text, "Цвет", "categorical", "красный", "", "красный" if short_quote else text
    )
    assert not result.items
    assert result.review and result.rejections


@pytest.mark.parametrize(
    ("attribute", "kind", "text", "value", "unit", "quote"),
    [
        ("NFC", "boolean", "NFC: возможно поддерживается", "Да", "", "поддерживается"),
        ("Мощность", "numeric", "Мощность: возможно 100 Вт", "100", "Вт", "100 Вт"),
        ("Материал", "free", "Материал: возможно сталь", "сталь", "", "сталь"),
        ("Материал", "free", "Материал: сталь или пластик", "сталь", "", "сталь"),
    ],
)
def test_speculation_is_not_limited_to_color(
    attribute: str, kind: str, text: str, value: str, unit: str, quote: str
) -> None:
    _, result = extract(text, attribute, kind, value, unit, quote)
    assert not result.items
    assert result.rejections


def test_independent_exact_field_survives_uncertain_neighbor() -> None:
    text = "Мощность: 100 Вт; Цвет: возможно красный"
    card, result = extract(text, "Мощность", "numeric", "100", "Вт", "Мощность: 100 Вт")
    assert len(result.items) == 1
    risk = assess_extraction(card, result)[0]
    assert AcceptancePolicy().accepts(risk, 7)


def test_real_compatibility_list_is_not_an_unresolved_alternative() -> None:
    text = "Модель совместима с Android и iOS"
    _, result = extract(text, "Совместимые операционные системы", "free", "Android, iOS", "", text)
    assert len(result.items) == 1


@pytest.mark.parametrize("text", ["Цвет: возможно, красный", "Возможно, цвет: красный"])
def test_introductory_speculation_survives_clause_boundaries(text: str) -> None:
    _, result = extract(text, "Цвет", "categorical", "красный", "", "красный")
    assert not result.items
    assert result.rejections


def test_tolerance_outside_numeric_quote_cannot_become_exact() -> None:
    _, result = extract("Мощность: 100 Вт ± 5%", "Мощность", "numeric", "100", "Вт", "100 Вт")
    assert not result.items
    assert result.rejections
