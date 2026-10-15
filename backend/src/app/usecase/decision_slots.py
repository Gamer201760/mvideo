from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

from app.domain.values import canonical_key
from app.usecase.baseline_ports import GoldRecord
from app.usecase.decision_stage import StageResult, baseline_picks
from app.usecase.extraction import CardExtraction


@dataclass(slots=True)
class SlotBook:
    eligible: int = 0
    routed: int = 0
    with_gold: int = 0
    baseline_correct: int = 0
    decision_correct: int = 0
    decision_answered: int = 0
    by_attribute: dict[str, list[int]] = field(default_factory=dict)

    def add(self, base: CardExtraction, result: StageResult,
            gold: Sequence[GoldRecord]) -> Iterator[tuple[float, bool]]:
        self.eligible += result.eligible
        self.routed += result.questions
        truth = {g.attribute: g for g in gold}
        before = baseline_picks(base)
        for slot in result.slots:
            record = truth.get(slot.attribute)
            profile = base.profiles.get(slot.attribute)
            if record is None or profile is None:
                continue
            expected = canonical_key(record.value, record.unit, profile.numeric)
            old = before.get(slot.attribute)
            new = result.chosen.get(slot.attribute)
            row = self.by_attribute.setdefault(slot.attribute, [0, 0, 0, 0])
            self.with_gold += 1
            row[0] += 1
            if old is not None and old.candidate.key == expected:
                self.baseline_correct += 1
                row[1] += 1
            if new is not None and new.candidate is not None:
                self.decision_answered += 1
                hit = new.candidate.key == expected
                self.decision_correct += 1 if hit else 0
                row[2] += 1 if hit else 0
                row[3] += 1
                yield new.probability, hit

    def summary(self) -> dict[str, object]:
        ranked = sorted(self.by_attribute.items(), key=lambda kv: -kv[1][0])
        return {
            "eligible_slots": self.eligible,
            "routed_slots": self.routed,
            "routed_share": round(self.routed / self.eligible, 4) if self.eligible else 0.0,
            "routed_with_gold": self.with_gold,
            "baseline_correct": self.baseline_correct,
            "decision_correct": self.decision_correct,
            "decision_answered": self.decision_answered,
            "attributes": {name: {"slots": r[0], "baseline_correct": r[1],
                                  "decision_correct": r[2], "decision_answered": r[3]}
                           for name, r in ranked},
        }
