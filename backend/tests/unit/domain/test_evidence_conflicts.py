import pytest

from app.domain.attribute_evidence import parse_answer
from app.domain.attribute_flow import CatalogField
from app.domain.evidence_validation import evidence_error


@pytest.mark.parametrize(
    ("attribute", "text", "value"),
    [
        ("Модель", "Модель ABC. Модель XYZ.", "ABC"),
        ("Бренд", "Бренд Nordwell\nБренд Southwell", "Nordwell"),
        ("Цвет", "Цвет красный\nЦвет синий", "красный"),
        ("Цвет", "Цвет: красный\nЦвет синий", "красный"),
    ],
)
def test_plain_declarations_cannot_hide_conflicting_values(
    attribute: str, text: str, value: str
) -> None:
    answer = parse_answer({"v": value, "u": "", "q": value}, attribute, text)
    assert evidence_error(answer, CatalogField(attribute, "free", ""), text) == "conflicting_values"


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("Модель ABC\nМодель ABC", "ABC"),
        ("Модель : ABC\nМодель ABC", "ABC"),
        ("Модель не ABC. Модель XYZ", "XYZ"),
    ],
)
def test_repetition_and_rejected_alternatives_are_not_conflicts(text: str, value: str) -> None:
    answer = parse_answer({"v": value, "u": "", "q": value}, "Модель", text)
    assert evidence_error(answer, CatalogField("Модель", "free", ""), text) is None
