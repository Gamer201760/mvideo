from app.domain.calibration import (
    ScoredPick,
    best_threshold,
    expected_calibration_error,
    reliability,
    threshold_curve,
)
from app.domain.candidate import Candidate, Source
from app.domain.profile import AttributeProfile, Kind
from app.domain.ranker_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, rank_options

COLOR = AttributeProfile("Цвет", Kind.CATEGORICAL, "", ("цвет",))


def candidate(key: str, source: str, zone: str, start: int) -> Candidate:
    return Candidate("Цвет", key, key, key, start, start + len(key), source, zone, 0.5, 0.2, 0)


def test_options_group_candidates_by_key_and_rank_them() -> None:
    candidates = [
        candidate("черный", Source.DICTIONARY, "title", 10),
        candidate("черный", Source.SELLER, "seller", 80),
        candidate("белый", Source.DICTIONARY, "description", 40),
    ]
    options = rank_options(candidates, {"Цвет": COLOR}, text_length=100)
    by_key = {o.key: o for o in options}
    assert set(by_key) == {"черный", "белый"}
    black, white = by_key["черный"], by_key["белый"]
    assert len(black.numeric) == len(NUMERIC_FEATURES)
    assert len(black.categorical) == len(CATEGORICAL_FEATURES)
    features = dict(zip(NUMERIC_FEATURES, black.numeric, strict=True))
    assert features["candidates"] == 2 and features["sources"] == 2
    assert features["heuristic_rank"] == 0 and features["heuristic_gap"] == 0
    assert dict(zip(NUMERIC_FEATURES, white.numeric, strict=True))["heuristic_rank"] == 1
    assert black.candidate.zone == "seller" and black.sources == ("dictionary", "seller")


def test_reliability_and_ece() -> None:
    table = reliability([0.95, 0.95, 0.15, 0.15], [True, True, False, True])
    assert table[9].count == 2 and table[9].accuracy == 1.0
    assert table[1].count == 2 and table[1].accuracy == 0.5
    assert abs(expected_calibration_error(table) - 0.2) < 1e-9


def test_threshold_curve_and_best_threshold() -> None:
    picks = [ScoredPick(0.9, True, True), ScoredPick(0.6, True, False),
             ScoredPick(0.3, True, True), ScoredPick(0.8, False, False)]
    points = threshold_curve(picks, gold=3, pairs=5, thresholds=(0.2, 0.5, 0.7))
    assert [round(p.precision, 3) for p in points] == [0.667, 0.5, 1.0]
    assert [round(p.coverage, 2) for p in points] == [0.8, 0.6, 0.4]
    assert best_threshold(points).threshold == 0.2
