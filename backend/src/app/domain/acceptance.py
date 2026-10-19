import math
from dataclasses import dataclass

from app.domain.evidence_risk import AttributeRisk


@dataclass(frozen=True, slots=True)
class AcceptancePolicy:
    threshold: float = 0.95
    enabled: bool = True

    def __post_init__(self) -> None:
        if not math.isfinite(self.threshold) or not 0 < self.threshold <= 1:
            raise ValueError("Acceptance threshold must be greater than zero and at most one")

    def accepts(self, risk: AttributeRisk | None, category_id: int | None) -> bool:
        return bool(
            self.enabled
            and category_id is not None
            and category_id >= 0
            and risk is not None
            and risk.level == "low"
            and math.isfinite(risk.score)
            and risk.score >= self.threshold
            and risk.score <= 1
            and {"exact_quote", "value_supported", "category_field"} <= set(risk.reasons)
            and set(risk.reasons)
            <= {"exact_quote", "value_supported", "category_field", "number_supported"}
        )
