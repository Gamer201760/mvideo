from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import cast

from app.domain.calibration import (
    ReliabilityBin,
    ThresholdPoint,
    expected_calibration_error,
    reliability,
)
from app.domain.metrics import MetricsBook
from app.domain.scoring import Pick
from app.usecase.ranker_pass import Scored
from app.usecase.ranker_ports import FeatureTable
from app.usecase.report import build_report, render_markdown

ABLATION_GROUPS = (
    "all", "split:test", "split:new_category", "categories:tail", "sellers:small",
    "category:smartphones", "category:laptops",
)
TOP_IMPORTANCES = 15
THRESHOLD_RULE = ("порог максимизирует micro F1 на val по откалиброванной уверенности, "
                  "сетка 0,05–0,95 с шагом 0,05; при равенстве — меньший порог")


@dataclass(slots=True)
class CalibrationLog:
    raw: list[float] = field(default_factory=list)
    calibrated: list[float] = field(default_factory=list)
    correct: list[bool] = field(default_factory=list)
    heuristic: list[float] = field(default_factory=list)
    heuristic_correct: list[bool] = field(default_factory=list)

    def add(self, scored: Scored, confidences: Mapping[str, float],
            baseline: Mapping[str, Pick]) -> None:
        expected = scored.item.expected
        for name, choice in scored.choices.items():
            truth = expected.get(name)
            if truth is not None:
                self.raw.append(choice.raw)
                self.calibrated.append(confidences[name])
                self.correct.append(choice.option.key == truth)
        for name, pick in baseline.items():
            truth = expected.get(name)
            if truth is not None:
                self.heuristic.append(pick.confidence)
                self.heuristic_correct.append(pick.candidate.key == truth)


def _calibration(values: Sequence[float], correct: Sequence[bool]) -> dict[str, object]:
    table: list[ReliabilityBin] = reliability(values, correct)
    return {"ece": round(expected_calibration_error(table), 4), "picks": len(values),
            "bins": [{k: round(v, 4) if isinstance(v, float) else v for k, v in asdict(b).items()}
                     for b in table]}


def _summary(groups: Mapping[str, object], group: str) -> dict[str, float] | None:
    data = groups.get(group)
    if not isinstance(data, Mapping):
        return None
    micro = cast(Mapping[str, float], data["micro"])
    weighted = cast(Mapping[str, float], data["weighted"])
    return {"precision": micro["precision"], "recall": micro["recall"], "f1": micro["f1"],
            "coverage_after": micro["coverage_after"], "macro_f1": cast(float, data["macro_f1"]),
            "weighted_f1": weighted["f1"]}


def _ablation(report: Mapping[str, object], baseline: Mapping[str, object] | None) -> list[object]:
    rows: list[object] = []
    ours = cast(Mapping[str, object], report["groups"])
    theirs = cast(Mapping[str, object], baseline.get("groups", {})) if baseline else {}
    for group in ABLATION_GROUPS:
        rows.append({"group": group, "baseline": _summary(theirs, group),
                     "ranker": _summary(ours, group)})
    return rows


def build_ranker_report(
    plain: MetricsBook, weighted: MetricsBook, *, cards: int, lexicon_entries: int,
    attributes: int, train: FeatureTable, threshold: float, curve: Sequence[ThresholdPoint],
    calibration: CalibrationLog, importances: Mapping[str, float],
    baseline: Mapping[str, object] | None, seconds: float,
) -> dict[str, object]:
    report = build_report(plain, weighted, cards=cards, lexicon_entries=lexicon_entries,
                          attributes=attributes)
    report["stage"] = "ranker: gradient boosting over candidates + isotonic calibration"
    report["confidence_calibrated"] = True
    positives = sum(train.labels)
    report["model"] = {
        "train_rows": train.rows,
        "positive_share": round(positives / train.rows, 4) if train.rows else 0.0,
        "importances": dict(sorted(importances.items(), key=lambda kv: -kv[1])[:TOP_IMPORTANCES]),
    }
    report["threshold"] = {"value": threshold, "rule": THRESHOLD_RULE,
                           "curve_val": [{k: round(v, 4) for k, v in asdict(p).items()}
                                         for p in curve]}
    report["calibration"] = {
        "split": "test + new_category",
        "heuristic": _calibration(calibration.heuristic, calibration.heuristic_correct),
        "raw": _calibration(calibration.raw, calibration.correct),
        "calibrated": _calibration(calibration.calibrated, calibration.correct),
    }
    report["ablation"] = _ablation(report, baseline)
    report["seconds"] = seconds
    return report


def _pct(value: object) -> str:
    return "—" if value is None else f"{float(cast(float, value)) * 100:.1f}"


def _row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _ablation_lines(rows: Sequence[Mapping[str, object]]) -> list[str]:
    keys = ("precision", "recall", "f1", "coverage_after", "weighted_f1")
    lines = ["## Абляция: базлайн → ранжировщик", "",
             _row(["срез", "ступень", "P", "R", "F1", "покрытие", "F1 взвеш."]),
             _row(["---"] * 7)]
    for row in rows:
        for stage in ("baseline", "ranker"):
            values = cast(Mapping[str, float] | None, row[stage])
            cells = [_pct(values[k]) if values else "—" for k in keys]
            lines.append(_row([str(row["group"]), stage, *cells]))
    return lines


def _calibration_lines(calibration: Mapping[str, Mapping[str, object]]) -> list[str]:
    lines = ["", "## Калибровка уверенности (test + new_category)", "",
             _row(["уверенность", "выборов с эталоном", "ECE"]), _row(["---"] * 3)]
    titles = {"heuristic": "эвристика базлайна", "raw": "модель до калибровки",
              "calibrated": "после isotonic"}
    for key, title in titles.items():
        data = calibration[key]
        lines.append(_row([title, str(data["picks"]), f"{float(cast(float, data['ece'])):.4f}"]))
    lines += ["", "Reliability-диаграмма после калибровки:", "",
              _row(["бин", "выборов", "средняя уверенность", "доля верных"]), _row(["---"] * 4)]
    for b in cast(Sequence[Mapping[str, float]], calibration["calibrated"]["bins"]):
        lines.append(_row([f"{b['low']:.1f}–{b['high']:.1f}", str(int(b["count"])),
                           _pct(b["confidence"]), _pct(b["accuracy"])]))
    return lines


def render_ranker_markdown(report: Mapping[str, object]) -> str:
    base = render_markdown(report).split("\n")
    base[0] = "# Отчёт метрик: ранжировщик кандидатов"
    base[2] = (f"Карточек: {report['cards']}; уверенность откалибрована (isotonic на val). "
               "Файл генерируется командой оценки и руками не правится.")
    threshold = cast(Mapping[str, object], report["threshold"])
    lines = ["", *_ablation_lines(cast(Sequence[Mapping[str, object]], report["ablation"]))]
    lines += _calibration_lines(cast(Mapping[str, Mapping[str, object]], report["calibration"]))
    lines += ["", "## Порог", "", f"Выбран порог {threshold['value']}: {threshold['rule']}.", "",
              _row(["порог", "P", "R", "F1", "покрытие"]), _row(["---"] * 5)]
    for p in cast(Sequence[Mapping[str, float]], threshold["curve_val"]):
        lines.append(_row([f"{p['threshold']:.2f}", _pct(p["precision"]), _pct(p["recall"]),
                           _pct(p["f1"]), _pct(p["coverage"])]))
    model = cast(Mapping[str, object], report["model"])
    lines += ["", "## Модель", "",
              (f"Строк обучения: {model['train_rows']}; доля верных кандидатов: "
              f"{_pct(model['positive_share'])} %."), "",
              _row(["признак", "важность"]), _row(["---"] * 2)]
    for name, value in cast(Mapping[str, float], model["importances"]).items():
        lines.append(_row([name, f"{value:.2f}"]))
    return "\n".join([*base, *lines, ""])
