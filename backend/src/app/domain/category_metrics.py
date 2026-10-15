from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.category_guess import Ranked

CURVE_THRESHOLDS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


@dataclass(frozen=True, slots=True)
class CurvePoint:
    threshold: float
    coverage: float
    precision: float


def top_k_accuracy(truth: Sequence[int], ranked: Sequence[Ranked], k: int) -> float:
    if not truth:
        return 0.0
    hits = sum(1 for t, r in zip(truth, ranked, strict=True) if t in {c for c, _ in r[:k]})
    return hits / len(truth)


def macro_f1(truth: Sequence[int], predicted: Sequence[int]) -> float:
    tp: Counter[int] = Counter()
    fp: Counter[int] = Counter()
    fn: Counter[int] = Counter()
    for t, p in zip(truth, predicted, strict=True):
        if t == p:
            tp[t] += 1
        else:
            fp[p] += 1
            fn[t] += 1
    labels = set(truth)
    if not labels:
        return 0.0
    scores = []
    for label in labels:
        denominator = 2 * tp[label] + fp[label] + fn[label]
        scores.append(2 * tp[label] / denominator if denominator else 0.0)
    return sum(scores) / len(scores)


def curve(
    truth: Sequence[int], ranked: Sequence[Ranked], thresholds: Sequence[float] = CURVE_THRESHOLDS
) -> list[CurvePoint]:
    points = []
    total = len(truth)
    for threshold in thresholds:
        accepted = [(t, r[0][0]) for t, r in zip(truth, ranked, strict=True)
                    if r and r[0][1] >= threshold]
        correct = sum(1 for t, p in accepted if t == p)
        points.append(CurvePoint(
            threshold,
            len(accepted) / total if total else 0.0,
            correct / len(accepted) if accepted else 0.0,
        ))
    return points


def histogram(values: Sequence[float], bins: int = 10) -> list[int]:
    counts = [0] * bins
    for value in values:
        counts[min(int(value * bins), bins - 1)] += 1
    return counts


def rejection_threshold(values: Sequence[float], reject_share: float, step: float = 0.01) -> float:
    if not values:
        return 0.0
    for i in range(int(1 / step) + 1):
        threshold = round(i * step, 4)
        if sum(1 for v in values if v < threshold) / len(values) >= reject_share:
            return threshold
    return 1.0


def acceptance(values: Sequence[float], threshold: float) -> float:
    return sum(1 for v in values if v >= threshold) / len(values) if values else 0.0


def pick_threshold(
    truth: Sequence[int], ranked: Sequence[Ranked], target_precision: float, step: float = 0.01
) -> float:
    candidates = [round(i * step, 4) for i in range(int(1 / step) + 1)]
    for point in curve(truth, ranked, candidates):
        if point.coverage > 0 and point.precision >= target_precision:
            return point.threshold
    return 1.0
