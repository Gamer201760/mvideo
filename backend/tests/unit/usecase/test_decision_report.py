from app.domain.inference import Usage
from app.usecase.decision_report import BUDGET_SKIP, CalibrationBook, UsageBook
from app.usecase.decision_stage import StageResult


def test_calibration_summary_reports_overconfidence() -> None:
    book = CalibrationBook()
    book.extend([(0.95, False)] * 9 + [(0.95, True)])

    summary = book.summary()

    assert summary["pairs"] == 10
    assert summary["ece"] == 0.85
    assert summary["bins"] == [{"low": 0.9, "high": 1.0, "count": 10, "mean_confidence": 0.95,
                                "accuracy": 0.1}]


def test_usage_uses_reported_cost_per_card() -> None:
    usage = UsageBook()
    result = StageResult((), {}, {}, Usage("jev", 300, 1000, 100, 0.0001), False, 4)
    usage.add(result, None)
    usage.add(result, None)
    usage.add(None, BUDGET_SKIP)
    usage.add(None, "HTTP 500")

    summary = usage.summary(None, None)

    assert summary["live_calls"] == 2
    assert summary["budget_skips"] == 1
    assert summary["failures"] == 1
    assert summary["cost_usd_total"] == 0.0002
    assert summary["cost_usd_per_million_cards"] == 100.0
