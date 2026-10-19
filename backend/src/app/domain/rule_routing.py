from dataclasses import dataclass

from app.domain.attribute_flow import Extraction, FlowCard
from app.domain.attribute_normalization import normalize_answer
from app.domain.evidence_risk import assess_extraction
from app.domain.evidence_validation import validate_extraction
from app.domain.rule_text_coverage import text_covered


@dataclass(frozen=True, slots=True)
class RuleRoutingPolicy:
    min_coverage: float = 1.0
    min_category_score: float = 0.35
    min_category_margin: float = 0.1
    min_supported_fields: int = 2
    require_covered_text: bool = True

    def __post_init__(self) -> None:
        if (
            not all(
                0 <= v <= 1
                for v in (self.min_coverage, self.min_category_score, self.min_category_margin)
            )
            or self.min_supported_fields < 1
        ):
            raise ValueError("Invalid rule routing thresholds")


@dataclass(frozen=True, slots=True)
class RuleRoutingDecision:
    extraction: Extraction | None
    reason: str
    coverage: float = 0.0


def route_rules(card: FlowCard, policy: RuleRoutingPolicy) -> RuleRoutingDecision:
    if not card.candidates or not card.candidates[0].fields:
        return RuleRoutingDecision(None, "category_missing")
    category = card.candidates[0]
    alternative = max((c.score for c in card.candidates[1:]), default=0.0)
    if (
        category.score < policy.min_category_score
        or category.score - alternative < policy.min_category_margin
    ):
        return RuleRoutingDecision(None, "category_uncertain")
    definitions = {f.attribute: f for f in category.fields}
    answers = tuple(
        normalize_answer(a, definitions[a.attribute])
        for a in card.rules
        if a.attribute in definitions and a.status == "supported"
    )
    result = validate_extraction(
        Extraction(card.sku_id, category.category_id, answers, (), False),
        category.fields,
        card.text,
        category,
    )
    found = {a.attribute for a in result.items}
    coverage = len(found) / len(definitions)
    if result.review or len(found) != len(answers) or len(answers) != len(card.rules):
        return RuleRoutingDecision(None, "evidence_rejected", coverage)
    if len(found) < policy.min_supported_fields or coverage < policy.min_coverage:
        return RuleRoutingDecision(None, "fields_missing", coverage)
    if any(r.level != "low" for r in assess_extraction(card, result)):
        return RuleRoutingDecision(None, "evidence_uncertain", coverage)
    if policy.require_covered_text and not text_covered(card, result):
        return RuleRoutingDecision(None, "unparsed_text", coverage)
    return RuleRoutingDecision(result, "rules_sufficient", coverage)
