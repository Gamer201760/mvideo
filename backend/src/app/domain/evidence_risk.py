import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Literal

from app.domain.attribute_flow import CatalogCandidate, Extraction, FlowCard
from app.domain.evidence_signals import NAMES, evidence_signals
from app.domain.evidence_validation import evidence_error

RiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class AttributeRisk:
    attribute: str
    level: RiskLevel
    reasons: tuple[str, ...]
    score: float
    method: Literal["heuristic", "catalog_proxy"]


@dataclass(frozen=True, slots=True)
class EvidenceRiskModel:
    coefficients: tuple[float, ...]
    intercept: float
    low_threshold: float
    high_threshold: float

    def __post_init__(self) -> None:
        if len(self.coefficients) != len(NAMES):
            raise ValueError("risk feature count differs")
        if not all(
            math.isfinite(v)
            for v in (*self.coefficients, self.intercept, self.low_threshold, self.high_threshold)
        ):
            raise ValueError("risk model contains a non-finite value")
        if not 0 <= self.high_threshold <= self.low_threshold <= 1.01:
            raise ValueError("risk thresholds are invalid")

    def score(self, features: Mapping[str, float]) -> float:
        logit = self.intercept + sum(
            c * features[n] for c, n in zip(self.coefficients, NAMES, strict=True)
        )
        return 1 / (1 + math.exp(-max(-50, min(50, logit))))


def assess_features(
    attribute: str, f: Mapping[str, float], model: EvidenceRiskModel | None = None
) -> AttributeRisk:
    reasons = []
    for feature, reason in (
        ("number_unconfirmed", "number_unconfirmed"),
        ("context_negation", "negation"),
        ("other_object", "object_context"),
        ("range_lost", "range_lost"),
        ("conflicting_values", "conflicting_values"),
        ("model_scope", "model_scope"),
        ("model_conflict", "model_conflict"),
        ("model_inference", "model_inference"),
    ):
        if f[feature]:
            reasons.append(reason)
    if f["value_overlap"] < 0.5 and not f["number_supported"]:
        reasons.append("indirect_value")
    if not f["field_overlap"] and not f["named_value"]:
        reasons.append("field_unconfirmed")
    if f["category_rank"] > 0 or f["category_margin"] < 0.05:
        reasons.append("category_ambiguity")
    severe = bool(f["range_lost"] or f["conflicting_values"] or f["model_conflict"])
    score = max(0.0, 1 - 0.15 * len(reasons) - 0.35 * severe)
    method: Literal["heuristic", "catalog_proxy"] = "heuristic"
    low, high = 0.85, 0.5
    if model is not None and f["known_field"] and not f["seller_source"]:
        score, method = model.score(f), "catalog_proxy"
        low, high = model.low_threshold, model.high_threshold
    advisory = (method == "heuristic" and bool(reasons)) or bool(
        f["model_scope"] or f["model_inference"]
    )
    level: RiskLevel = (
        "high" if severe or score < high else "medium" if advisory or score < low else "low"
    )
    uncertain = any(
        f[n]
        for n in (
            "number_unconfirmed",
            "context_negation",
            "other_object",
            "range_lost",
            "conflicting_values",
            "model_scope",
            "model_conflict",
            "model_inference",
        )
    )
    if (
        not uncertain
        and (f["value_overlap"] == 1 or f["number_supported"])
        and (f["named_value"] or f["field_overlap"])
    ):
        reasons.append("value_supported")
    if f["number_supported"]:
        reasons.append("number_supported")
    if f["known_field"]:
        reasons.append("category_field")
    return AttributeRisk(attribute, level, tuple(reasons), round(score, 6), method)


def assess_extraction(
    card: FlowCard, extraction: Extraction, model: EvidenceRiskModel | None = None
) -> tuple[AttributeRisk, ...]:
    category = next((c for c in card.candidates if c.category_id == extraction.category_id), None)
    if category is None:
        category = CatalogCandidate(-1, extraction.proposed_category or "", 0, ())
        model = None
    assessments = []
    for answer in (*extraction.items, *extraction.extra_fields):
        if answer.status != "supported":
            continue
        if (
            not answer.quote
            or answer.start < 0
            or card.text[answer.start : answer.end] != answer.quote
        ):
            assessments.append(
                AttributeRisk(answer.attribute, "high", ("invalid_evidence",), 0.0, "heuristic")
            )
        else:
            definition = next((f for f in category.fields if f.attribute == answer.attribute), None)
            error = evidence_error(answer, definition, card.text, category)
            if error:
                assessments.append(
                    AttributeRisk(
                        answer.attribute, "high", ("exact_quote", error), 0.0, "heuristic"
                    )
                )
                continue
            risk = assess_features(
                answer.attribute, evidence_signals(card, category, answer), model
            )
            assessments.append(replace(risk, reasons=("exact_quote", *risk.reasons)))
    return tuple(assessments)
