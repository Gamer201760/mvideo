from dataclasses import dataclass

from app.domain.attribute_flow import EvidenceRejection
from app.domain.evidence_risk import AttributeRisk


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtractedValue:
    attribute: str
    value: str
    confidence: float
    source: str
    sources: tuple[str, ...]
    evidence: str
    start: int
    end: int
    in_review: bool
    review_id: str | None
    risk: AttributeRisk | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CardResult:
    text: str
    threshold: float
    values: tuple[ExtractedValue, ...]
    missing: tuple[str, ...]
    rejections: tuple[EvidenceRejection, ...] = ()
    auto_accept_enabled: bool = True
