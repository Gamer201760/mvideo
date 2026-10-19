import pytest

from app.domain.attribute_evidence import parse_batch
from app.domain.attribute_flow import FlowCard
from app.domain.evidence_risk import assess_extraction
from app.usecase.attribute_flow_contract import make_request


def answer(category: object, quote: str = "845 л.с.") -> dict[str, object]:
    return {
        "c": [
            {
                "i": 0,
                "k": category,
                "a": [
                    {"f": "Мощность", "v": "845", "u": "л.с.", "q": quote, "r": 0},
                ],
                "r": [],
            }
        ]
    }


def test_new_category_keeps_supported_fields_without_catalog_candidates() -> None:
    card = FlowCard(1, "Электрический пикап\nМощность: 845 л.с.", ())
    result = parse_batch(answer("Транспорт / Электрические пикапы"), (card,))[0]
    assert result.proposed_category == "Транспорт / Электрические пикапы"
    assert result.category_id is None
    field = result.extra_fields[0]
    assert card.text[field.start : field.end] == field.quote == "845 л.с."
    assert assess_extraction(card, result)[0].method == "heuristic"
    request = make_request((card,), (result,))
    assert result.proposed_category in request.prompt


def test_null_category_does_not_discard_supported_named_attributes() -> None:
    card = FlowCard(1, "845 л.с.", ())
    result = parse_batch(answer(None), (card,))[0]
    assert len(result.extra_fields) == 1
    assert result.proposed_category is None


def test_new_category_cannot_bypass_quote_validation() -> None:
    result = parse_batch(answer("Пикапы", "900 л.с."), (FlowCard(1, "845 л.с.", ()),))[0]
    assert not result.extra_fields
    assert result.review


@pytest.mark.parametrize("category", ["", "  ", "x" * 201, True])
def test_invalid_proposed_categories_are_rejected(category: object) -> None:
    with pytest.raises(ValueError):
        parse_batch(answer(category), (FlowCard(1, "845 л.с.", ()),))
