import pytest

from app.domain.attribute_evidence import parse_answer, parse_batch
from app.domain.attribute_flow import CatalogCandidate, CatalogField, Extraction, FlowCard
from app.domain.evidence_risk import assess_extraction


def result_for(attribute: str, text: str, value: str, quote: str) -> Extraction:
    fields = (
        CatalogField("Бренд", "categorical", "", ("Nordwell", "красный")),
        CatalogField("Модель", "free", ""),
        CatalogField("Цвет", "categorical", ""),
    )
    card = FlowCard(1, text, (CatalogCandidate(7, "Товары / Смартфоны", 0.99, fields),))
    index = next(i for i, f in enumerate(fields) if f.attribute == attribute)
    return parse_batch(
        {"c": [{"i": 0, "k": 0, "a": [{"f": index, "v": value, "u": "", "q": quote}], "r": []}]},
        (card,),
    )[0]


@pytest.mark.parametrize(
    ("attribute", "text", "value", "quote"),
    [
        ("Бренд", "Цвет красный", "красный", "красный"),
        ("Бренд", "Цвет красный", "красный", "Цвет красный"),
        ("Бренд", "Цвет красный\nОписание", "красный", "красный"),
        ("Бренд", "Смартфон\nЦвет Nordwell", "Nordwell", "Nordwell"),
        ("Модель", "Модель не ABC", "ABC", "ABC"),
        ("Модель", "Модель не ABC", "ABC", "Модель не ABC"),
        ("Модель", "Модель: не ABC", "ABC", "ABC"),
        ("Модель", "Модель не является ABC", "ABC", "ABC"),
        ("Модель", "Это не модель ABC", "ABC", "ABC"),
        ("Модель", "Модель не ABC", "не ABC", "не ABC"),
        ("Модель", "Смартфон\nЭто не модель ABC", "ABC", "ABC"),
        ("Модель", "Цвет ABC", "ABC", "ABC"),
    ],
)
def test_other_fields_and_negated_identity_are_not_values(
    attribute: str, text: str, value: str, quote: str
) -> None:
    result = result_for(attribute, text, value, quote)
    assert not result.items
    assert result.rejections[0].reason in {
        "negation",
        "field_mismatch",
        "field_unconfirmed",
        "value_unconfirmed",
    }


@pytest.mark.parametrize(
    ("attribute", "text", "value", "quote"),
    [
        ("Бренд", "Бренд красный", "красный", "красный"),
        ("Бренд", "Бренд: Nordwell", "Nordwell", "Nordwell"),
        ("Бренд", "Смартфон Nordwell\nОписание", "Nordwell", "Nordwell"),
        ("Модель", "Смартфон Nordwell ABC\nОписание", "ABC", "ABC"),
        ("Модель", "Модель ABC", "ABC", "ABC"),
        ("Модель", "Модель не ABC, а XYZ", "XYZ", "XYZ"),
    ],
)
def test_affirmative_identity_is_preserved(
    attribute: str, text: str, value: str, quote: str
) -> None:
    assert len(result_for(attribute, text, value, quote).items) == 1


@pytest.mark.parametrize(
    ("attribute", "text", "value"),
    [
        ("Бренд", "Цвет красный", "красный"),
        ("Модель", "Модель не ABC", "ABC"),
    ],
)
def test_invalid_entity_never_receives_confirmation_points(
    attribute: str, text: str, value: str
) -> None:
    field = CatalogField(attribute, "free", "")
    category = CatalogCandidate(7, "Смартфоны", 0.99, (field,))
    card = FlowCard(1, text, (category,))
    answer = parse_answer({"v": value, "u": "", "q": value}, attribute, text)
    risk = assess_extraction(card, Extraction(1, 7, (answer,), (), False))[0]
    assert risk.score == 0
    assert risk.level == "high"
