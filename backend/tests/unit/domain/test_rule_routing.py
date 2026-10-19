from dataclasses import replace

import pytest
from tests.unit.domain.routing_cases import complete_card

from app.domain.rule_routing import RuleRoutingPolicy, route_rules


def test_complete_validated_schema_can_skip_the_model() -> None:
    decision = route_rules(complete_card(), RuleRoutingPolicy())
    assert decision.extraction is not None
    assert decision.coverage == 1
    assert decision.reason == "rules_sufficient"
    assert len(decision.extraction.items) == 2


@pytest.mark.parametrize(
    "case",
    [
        "unknown",
        "weak_category",
        "close_categories",
        "missing",
        "contradiction",
        "duplicate",
        "risk",
    ],
)
def test_uncertain_or_incomplete_rules_require_the_model(case: str) -> None:
    card = complete_card()
    category = card.candidates[0]
    if case == "unknown":
        card = replace(card, candidates=())
    elif case == "weak_category":
        card = replace(card, candidates=(replace(category, score=0.2),))
    elif case == "close_categories":
        card = replace(card, candidates=(category, replace(category, category_id=8, score=0.85)))
    elif case == "missing":
        card = replace(card, rules=card.rules[:1])
    elif case == "contradiction":
        card = replace(card, rules=(replace(card.rules[0], value="синий"), card.rules[1]))
    elif case == "duplicate":
        card = replace(card, rules=(*card.rules, card.rules[0]))
    else:
        card = replace(card, rules=(replace(card.rules[0], risks=4), card.rules[1]))
    assert route_rules(card, RuleRoutingPolicy()).extraction is None


@pytest.mark.parametrize("coverage", [-0.1, 1.1, float("nan")])
def test_invalid_policy_thresholds_are_rejected(coverage: float) -> None:
    with pytest.raises(ValueError):
        RuleRoutingPolicy(min_coverage=coverage)


@pytest.mark.parametrize(
    "addition",
    [
        "Материал: пластик",
        "Корпус из пластика",
        "Вес: 500 г, срок службы 2 года",
    ],
)
def test_unparsed_product_information_requires_the_model(addition: str) -> None:
    card = complete_card()
    card = replace(card, text=f"{card.text}\n{addition}")
    decision = route_rules(card, RuleRoutingPolicy())
    assert decision.extraction is None
    assert decision.reason == "unparsed_text"
    assert route_rules(card, RuleRoutingPolicy(require_covered_text=False)).extraction is not None


def test_unknown_information_in_title_cannot_be_ignored() -> None:
    card = complete_card()
    shift = len("водостойкий ")
    card = replace(
        card,
        text="водостойкий " + card.text,
        rules=tuple(replace(a, start=a.start + shift, end=a.end + shift) for a in card.rules),
    )
    assert route_rules(card, RuleRoutingPolicy()).reason == "unparsed_text"
