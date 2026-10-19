from dataclasses import replace

import pytest

from app.domain.acceptance import AcceptancePolicy
from app.domain.attribute_evidence import parse_answer
from app.domain.attribute_flow import CatalogCandidate, CatalogField, Extraction, FlowCard
from app.domain.evidence_risk import AttributeRisk, assess_extraction

RISK = AttributeRisk(
    "Цвет", "low", ("exact_quote", "value_supported", "category_field"), 0.95, "heuristic"
)


@pytest.mark.parametrize(("score", "accepted"), [(0.949, False), (0.95, True), (0.951, True)])
def test_threshold_boundary(score: float, accepted: bool) -> None:
    assert AcceptancePolicy().accepts(replace(RISK, score=score), 761) is accepted


@pytest.mark.parametrize("category", [None, -1])
def test_new_or_unknown_category_requires_review(category: int | None) -> None:
    assert not AcceptancePolicy().accepts(RISK, category)


@pytest.mark.parametrize(
    "risk",
    [
        None,
        replace(RISK, score=float("inf")),
        replace(RISK, level="medium", score=1),
        replace(RISK, level="high", score=1),
        replace(RISK, reasons=("exact_quote", "category_field")),
        replace(RISK, reasons=(*RISK.reasons, "model_inference")),
    ],
)
def test_high_score_does_not_bypass_evidence_constraints(risk: AttributeRisk | None) -> None:
    assert not AcceptancePolicy().accepts(risk, 761)


def test_review_only_mode_preserves_scores_but_disables_automatic_acceptance() -> None:
    assert not AcceptancePolicy(enabled=False).accepts(RISK, 761)


def test_implicit_value_without_field_link_does_not_receive_full_score() -> None:
    text = "Чайник черный"
    category = CatalogCandidate(7, "Чайники", 0.9, (CatalogField("Цвет", "categorical", ""),))
    card = FlowCard(1, text, (category,))
    answer = parse_answer({"v": "черный", "u": "", "q": "черный"}, "Цвет", text)
    risk = assess_extraction(card, Extraction(1, 7, (answer,), (), False))[0]
    assert risk.score < 0.95
    assert risk.level == "medium"
    assert "field_unconfirmed" in risk.reasons
    assert not AcceptancePolicy().accepts(risk, 7)


@pytest.mark.parametrize("threshold", [0, -1, 1.01, float("nan"), float("inf")])
def test_invalid_threshold_fails_configuration(threshold: float) -> None:
    with pytest.raises(ValueError):
        AcceptancePolicy(threshold)
