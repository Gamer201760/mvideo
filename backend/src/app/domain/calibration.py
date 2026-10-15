from collections.abc import Sequence
from dataclasses import dataclass

BINS = 10


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    low: float
    high: float
    count: int
    confidence: float
    accuracy: float


@dataclass(frozen=True, slots=True)
class ThresholdPoint:
    threshold: float
    precision: float
    recall: float
    f1: float
    coverage: float


@dataclass(frozen=True, slots=True)
class ScoredPick:
    confidence: float
    has_gold: bool
    correct: bool


def reliability(
    confidences: Sequence[float], correct: Sequence[bool], bins: int = BINS
) -> list[ReliabilityBin]:
    sums = [[0, 0.0, 0.0] for _ in range(bins)]
    for p, ok in zip(confidences, correct, strict=True):
        index = min(bins - 1, max(0, int(p * bins)))
        sums[index][0] += 1
        sums[index][1] += p
        sums[index][2] += 1.0 if ok else 0.0
    return [
        ReliabilityBin(i / bins, (i + 1) / bins, int(n), conf / n if n else 0.0,
                       hits / n if n else 0.0)
        for i, (n, conf, hits) in enumerate(sums)
    ]


def expected_calibration_error(table: Sequence[ReliabilityBin]) -> float:
    total = sum(b.count for b in table)
    if not total:
        return 0.0
    return sum(b.count * abs(b.confidence - b.accuracy) for b in table) / total


def threshold_curve(
    picks: Sequence[ScoredPick], gold: int, pairs: int, thresholds: Sequence[float]
) -> list[ThresholdPoint]:
    points = []
    for t in thresholds:
        kept = [p for p in picks if p.confidence >= t]
        judged = [p for p in kept if p.has_gold]
        tp = sum(1 for p in judged if p.correct)
        precision = tp / len(judged) if judged else 0.0
        recall = tp / gold if gold else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        points.append(ThresholdPoint(t, precision, recall, f1, len(kept) / pairs if pairs else 0.0))
    return points


def best_threshold(points: Sequence[ThresholdPoint]) -> ThresholdPoint:
    return max(points, key=lambda p: (round(p.f1, 6), -p.threshold))
