from collections.abc import Sequence
from dataclasses import dataclass, field

from app.domain.scoring import Pick
from app.domain.twin import Transfer
from app.usecase.baseline_ports import CardRecord

EXAMPLE_POOL = 400


@dataclass(frozen=True, slots=True)
class PairRecord:
    attribute: str
    has_gold: bool
    stage_predicted: bool
    stage_ok: bool
    similarity: float
    twin_ok: bool
    exact: bool
    false_twin: bool
    truth: str
    twin_value: str
    twin_sku: int

    @classmethod
    def of(
        cls, attribute: str, truth: str | None, pick: Pick | None, transfer: Transfer | None,
        model: str | None,
    ) -> "PairRecord":
        stage_ok = pick is not None and truth is not None and pick.candidate.key == truth
        if transfer is None:
            return cls(attribute, truth is not None, pick is not None, stage_ok, -1.0, False,
                       False, False, truth or "", "", 0)
        false_twin = bool(model and transfer.twin_model and model != transfer.twin_model)
        return cls(attribute, truth is not None, pick is not None, stage_ok, transfer.similarity,
                   truth is not None and transfer.key == truth, transfer.exact, false_twin,
                   truth or "", transfer.value, transfer.twin_sku)


@dataclass(frozen=True, slots=True)
class Example:
    sku_id: int
    title: str
    record: PairRecord


@dataclass(frozen=True, slots=True)
class CurvePoint:
    threshold: float
    precision: float
    recall: float
    f1: float
    transfers: int


@dataclass(slots=True)
class TuningLog:
    pairs: list[PairRecord] = field(default_factory=list)
    errors: list[Example] = field(default_factory=list)
    cards: dict[int, list[int]] = field(default_factory=dict)

    def add(self, record: PairRecord, card: CardRecord) -> None:
        self.cards.setdefault(card.sku_id, []).append(len(self.pairs))
        self.pairs.append(record)
        if record.similarity >= 0 and record.has_gold and not record.twin_ok \
                and len(self.errors) < EXAMPLE_POOL:
            self.errors.append(Example(card.sku_id, card.title or "", record))

    def summary(self, threshold: float) -> dict[str, object]:
        used = [p for p in self.pairs if p.similarity >= threshold]
        judged = [p for p in used if p.has_gold]
        exact = [p for p in judged if p.exact]
        inexact = [p for p in judged if not p.exact]
        twin_cards = [ids for ids in self.cards.values()
                      if any(self.pairs[i].similarity >= threshold for i in ids)]
        false_cards = [ids for ids in twin_cards
                       if any(self.pairs[i].similarity >= threshold and self.pairs[i].false_twin
                              for i in ids)]
        return {
            "cards": len(self.cards),
            "pairs": len(self.pairs),
            "transfers": len(used),
            "transfers_with_gold": len(judged),
            "transfer_precision": _share(judged),
            "exact_transfers": len(exact),
            "exact_precision": _share(exact),
            "inexact_transfers": len(inexact),
            "inexact_precision": _share(inexact),
            "cards_with_twin": len(twin_cards),
            "false_twin_cards": len(false_cards),
            "false_twin_rate": round(len(false_cards) / len(twin_cards), 4) if twin_cards else 0.0,
        }

    def examples(self, threshold: float, limit: int = 10) -> list[dict[str, object]]:
        chosen = sorted((e for e in self.errors if e.record.similarity >= threshold),
                        key=lambda e: (-e.record.similarity, e.sku_id))[:limit]
        return [{"sku_id": e.sku_id, "title": e.title[:120], "attribute": e.record.attribute,
                 "gold": e.record.truth, "twin_value": e.record.twin_value,
                 "twin_sku": e.record.twin_sku, "similarity": round(e.record.similarity, 4),
                 "exact": e.record.exact} for e in chosen]


def _share(records: Sequence[PairRecord]) -> float:
    return round(sum(1 for r in records if r.twin_ok) / len(records), 4) if records else 0.0


def curve_point(pairs: Sequence[PairRecord], threshold: float) -> CurvePoint:
    tp = fp = gold = transfers = 0
    for p in pairs:
        if not p.has_gold:
            continue
        gold += 1
        if p.stage_predicted:
            tp += p.stage_ok
            fp += not p.stage_ok
        elif p.similarity >= threshold:
            transfers += 1
            tp += p.twin_ok
            fp += not p.twin_ok
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / gold if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return CurvePoint(threshold, round(precision, 4), round(recall, 4), round(f1, 4), transfers)


def pick_threshold(
    pairs: Sequence[PairRecord], grid: Sequence[float]
) -> tuple[float, list[CurvePoint]]:
    curve = [curve_point(pairs, t) for t in grid]
    best = curve[0]
    for point in curve[1:]:
        if point.f1 >= best.f1:
            best = point
    return best.threshold, curve
