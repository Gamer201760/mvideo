from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import cast

from app.domain.calibration import ReliabilityBin, ThresholdPoint
from app.domain.fusion import FusionRules
from app.domain.metrics import MetricsBook
from app.usecase.final_stages import STAGES
from app.usecase.report import TOP_ATTRIBUTES

ABLATION_GROUPS = (
    "all", "split:test", "split:new_category", "categories:head", "categories:tail",
    "sellers:small", "category:smartphones", "category:laptops", "sample:decision",
)
DETAIL_GROUPS = ("category:smartphones", "category:laptops", "split:new_category", "all")
STAGE_TITLES = {
    "baseline": "базлайн", "ranker": "ранжировщик", "ranker+decision": "+ Jev",
    "ranker+decision+twins": "+ двойники", "fused": "сборка",
}


def _row_of(plain: MetricsBook, weighted: MetricsBook, group: str) -> dict[str, float]:
    micro = plain.micro(group)
    beyond = micro["recall"] - micro["recall_in_text"] * micro["ceiling"]
    return {**micro, "beyond_text": round(beyond, 4), "macro_f1": plain.macro_f1(group),
            "weighted_f1": weighted.micro(group)["f1"]}


def build_final_report(
    books: Mapping[str, tuple[MetricsBook, MetricsBook]], rules: FusionRules, *,
    threshold: float, val_curve: Sequence[ThresholdPoint], cards: int,
    reliability: Sequence[ReliabilityBin], ece: float, sources: Mapping[str, int], seconds: float,
) -> dict[str, object]:
    ablation = [
        {"stage": stage, "group": group, **_row_of(*books[stage], group)}
        for group in ABLATION_GROUPS for stage in STAGES if group in books[stage][0].groups
    ]
    fused, ranker = books["fused"][0], books["ranker"][0]
    details = {}
    for group in DETAIL_GROUPS:
        items = fused.attributes(group)
        limit = len(items) if group.startswith("category:") else TOP_ATTRIBUTES
        details[group] = {name: {**values, "ranker_f1": ranker.attributes(group).get(
            name, {}).get("f1", 0.0)} for name, values in list(items.items())[:limit]}
    return {
        "stage": "final fusion: rules per attribute and category mode, chosen on val",
        "confidence_calibrated": True,
        "cards": cards,
        "threshold": threshold,
        "rules": rules.to_json(),
        "ablation": ablation,
        "attributes": details,
        "val_curve": [asdict(p) for p in val_curve],
        "reliability": [asdict(b) for b in reliability],
        "ece": round(ece, 4),
        "sources": dict(sources),
        "seconds": seconds,
    }


def _pct(value: object) -> str:
    return f"{float(cast(float, value)) * 100:.1f}"


def _row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def render_final_markdown(report: Mapping[str, object]) -> str:
    rows = cast(Sequence[Mapping[str, object]], report["ablation"])
    rules = cast(Mapping[str, object], report["rules"])
    defaults = cast(Mapping[str, str], rules["defaults"])
    specific = cast(Sequence[Mapping[str, str]], rules["specific"])
    lines = [
        "# Итоговый отчёт: сборка источников и абляция",
        "",
        (f"Карточек test + new_category: {report['cards']}; порог уверенности {report['threshold']}"
         f" (подобран на val); ECE итоговой уверенности {report['ece']}. "
         "Файл генерируется командой `uv run final` и руками не правится."),
        "",
        "## Абляция",
        "",
        _row(["срез", "ступень", "P", "R", "F1", "macro F1", "F1 взвеш.", "R сверх текста",
              "покрытие до", "покрытие после"]),
        _row(["---"] * 10),
    ]
    for r in rows:
        lines.append(_row([str(r["group"]), STAGE_TITLES[str(r["stage"])], _pct(r["precision"]),
                           _pct(r["recall"]), _pct(r["f1"]), _pct(r["macro_f1"]),
                           _pct(r["weighted_f1"]), _pct(r["beyond_text"]),
                           _pct(r["coverage_before"]), _pct(r["coverage_after"])]))
    lines += ["", "## Правило выбора источника (подобрано на val)", "",
              (f"По умолчанию: известные категории — `{defaults.get('known')}`, новые — "
               f"`{defaults.get('new')}`. Отдельные правила для {len(specific)} атрибутов:"), "",
              _row(["атрибут", "режим", "правило"]), _row(["---"] * 3)]
    lines += [_row([s["attribute"], s["mode"], f"`{s['rule']}`"]) for s in specific]
    lines += ["", "## Источники значений в сборке", "", _row(["источник", "значений"]),
              _row(["---"] * 2)]
    lines += [_row([k, str(v)]) for k, v in cast(Mapping[str, int], report["sources"]).items()]
    lines += ["", "## Калибровка итоговой уверенности (test)", "",
              _row(["корзина", "пар", "средняя уверенность", "точность"]), _row(["---"] * 4)]
    for b in cast(Sequence[Mapping[str, float]], report["reliability"]):
        lines.append(_row([f"{b['low']:.1f}–{b['high']:.1f}", str(int(b["count"])),
                           f"{b['confidence']:.3f}", f"{b['accuracy']:.3f}"]))
    details = cast(Mapping[str, Mapping[str, Mapping[str, float]]], report["attributes"])
    for group, items in details.items():
        lines += ["", f"## По атрибутам: {group}", "",
                  _row(["атрибут", "пар с эталоном", "P", "R", "F1", "F1 ранжировщика"]),
                  _row(["---"] * 6)]
        lines += [_row([name, str(int(v["gold"])), _pct(v["precision"]), _pct(v["recall"]),
                        _pct(v["f1"]), _pct(v["ranker_f1"])]) for name, v in items.items()]
    return "\n".join(lines) + "\n"
