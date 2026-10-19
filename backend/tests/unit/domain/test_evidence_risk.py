from dataclasses import replace

import pytest

from app.domain.attribute_evidence import parse_answer
from app.domain.attribute_flow import CatalogCandidate, CatalogField, Extraction, FlowCard
from app.domain.evidence_risk import EvidenceRiskModel, assess_extraction
from app.domain.evidence_signals import NAMES, evidence_signals


def sample(
    text: str, value: str, unit: str = "", attribute: str = "Объем"
) -> tuple[FlowCard, CatalogCandidate, Extraction]:
    category = CatalogCandidate(7, "Чайники", 0.9, (CatalogField(attribute, "numeric", unit),))
    card = FlowCard(1, text, (category,))
    answer = parse_answer({"v": value, "u": unit, "q": text}, attribute, text)
    return card, category, Extraction(1, 7, (answer,), (), False)


def test_unit_conversion_is_supported_without_lexical_match() -> None:
    card, category, result = sample("Объем: 1700 мл", "1.7", "л")
    signals = evidence_signals(card, category, result.items[0])
    assert signals["value_overlap"] == 0
    assert signals["number_supported"] == 1
    assert "indirect_value" not in assess_extraction(card, result)[0].reasons


def test_preserved_range_is_not_penalized_as_a_dropped_range() -> None:
    card, _, result = sample("Время: до 20 часов", "до 20 часов", attribute="Время")
    assert "range_lost" not in assess_extraction(card, result)[0].reasons
    exact = replace(result.items[0], value="20", unit="ч")
    risk = assess_extraction(card, replace(result, items=(exact,)))[0]
    assert risk.level == "high" and "range_lost" in risk.reasons


def test_duplicate_measurements_in_compatible_units_are_not_conflicts() -> None:
    card, _, result = sample("Объем: 1700 мл\nОбъем: 1.7 л", "1.7", "л")
    assert "conflicting_values" not in assess_extraction(card, result)[0].reasons


def test_conflicting_values_raise_risk() -> None:
    card, _, result = sample("Объем: 1 л\nОбъем: 2 л", "1", "л")
    risk = assess_extraction(card, result)[0]
    assert risk.level == "high" and "conflicting_values" in risk.reasons


def test_exact_quote_is_not_enough_when_context_has_negation() -> None:
    card, _, result = sample("Зарядка не поддерживается", "Да", attribute="Зарядка")
    risk = assess_extraction(card, result)[0]
    assert risk.level != "low"
    assert "negation" in risk.reasons


def test_model_flags_do_not_become_a_probability() -> None:
    card, _, result = sample("Объем: 1 л", "1", "л")
    answer = replace(result.items[0], risks=3)
    model = EvidenceRiskModel((0.0,) * len(NAMES), 20.0, 0.8, 0.5)
    risk = assess_extraction(card, replace(result, items=(answer,)), model)[0]
    assert risk.level == "high"
    assert "model_conflict" in risk.reasons


def test_invalid_evidence_never_receives_low_risk() -> None:
    card, _, result = sample("Объем: 1 л", "1", "л")
    answer = replace(result.items[0], quote="invented")
    assert assess_extraction(card, replace(result, items=(answer,)))[0].level == "high"


@pytest.mark.parametrize("flags", [-1, 8, True, "2"])
def test_invalid_model_flags_are_rejected(flags: object) -> None:
    with pytest.raises(ValueError, match="risk flags"):
        parse_answer({"v": "1", "u": "", "q": "1", "r": flags}, "Объем", "1")


@pytest.mark.parametrize("ending", ["", ".", ". "])
def test_negation_from_next_sentence_does_not_affect_dimension(ending: str) -> None:
    text = "Экран 6,6 дюйма. NFC не поддерживается."
    card, category, result = sample(text, "6.6", '"', "Диагональ")
    quote = "Экран 6,6 дюйма" + ending
    answer = replace(result.items[0], quote=quote, start=0, end=len(quote))
    assert evidence_signals(card, category, answer)["context_negation"] == 0


def test_negative_value_supported_by_negative_statement_is_not_a_warning() -> None:
    card, _, result = sample("NFC не поддерживается", "нет", attribute="NFC")
    risk = assess_extraction(card, result)[0]
    assert "negation" not in risk.reasons
    assert "indirect_value" not in risk.reasons
