from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import cast

from app.domain.metrics import MetricsBook
from app.domain.twin import Transfer
from app.usecase.baseline_ports import CardRecord
from app.usecase.report import build_report, render_markdown
from app.usecase.twin_tuning import CurvePoint

ABLATION_KEYS = ("precision", "recall", "f1", "coverage_after")


@dataclass(slots=True)
class TwinLog:
    transfers: int = 0
    judged: int = 0
    correct: int = 0
    exact: Counter[bool] = field(default_factory=Counter)
    exact_ok: Counter[bool] = field(default_factory=Counter)
    attributes: Counter[str] = field(default_factory=Counter)
    cards: int = 0

    def add(self, card: CardRecord, scored: Mapping[str, tuple[Transfer, float]],
            expected: Mapping[str, str]) -> None:
        if scored:
            self.cards += 1
        for name, (transfer, _) in scored.items():
            self.transfers += 1
            self.attributes[name] += 1
            truth = expected.get(name)
            if truth is None:
                continue
            self.judged += 1
            ok = transfer.key == truth
            self.correct += ok
            self.exact[transfer.exact] += 1
            self.exact_ok[transfer.exact] += ok

    def summary(self) -> dict[str, object]:
        def share(ok: int, total: int) -> float:
            return round(ok / total, 4) if total else 0.0
        return {
            "cards_with_transfer": self.cards,
            "transfers": self.transfers,
            "transfers_with_gold": self.judged,
            "transfer_precision": share(self.correct, self.judged),
            "exact_transfers": self.exact[True],
            "exact_precision": share(self.exact_ok[True], self.exact[True]),
            "inexact_transfers": self.exact[False],
            "inexact_precision": share(self.exact_ok[False], self.exact[False]),
            "top_attributes": dict(self.attributes.most_common(15)),
        }


def _over_ceiling(micro: Mapping[str, float]) -> float:
    return round(micro["recall"] - micro["recall_in_text"] * micro["ceiling"], 4)


def _ablation(stage: Mapping[str, object], twins: Mapping[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group, data in cast(Mapping[str, Mapping[str, object]], twins["groups"]).items():
        before = cast(Mapping[str, Mapping[str, object]], stage["groups"]).get(group)
        if before is None:
            continue
        row: dict[str, object] = {"group": group}
        for stage_name, values in (("ranker", before), ("twins", data)):
            micro = cast(Mapping[str, float], values["micro"])
            weighted = cast(Mapping[str, float], values["weighted"])
            row[stage_name] = {**{k: micro[k] for k in ABLATION_KEYS},
                               "macro_f1": values["macro_f1"], "weighted_f1": weighted["f1"],
                               "recall_over_ceiling": _over_ceiling(micro)}
        rows.append(row)
    return rows


def build_twin_report(
    books: tuple[MetricsBook, MetricsBook, MetricsBook, MetricsBook], *, cards: int, entries: int,
    threshold: float, curve: Sequence[CurvePoint], tuning: Mapping[str, object],
    examples: Sequence[Mapping[str, object]], log: TwinLog, seconds: float,
) -> dict[str, object]:
    stage = build_report(books[0], books[1], cards=cards, lexicon_entries=0, attributes=0)
    twins = build_report(books[2], books[3], cards=cards, lexicon_entries=0, attributes=0)
    return {
        "stage": "twins: ranker + catalog twins (TF-IDF kNN over titles)",
        "confidence_calibrated": True,
        "cards": cards,
        "index_entries": entries,
        "threshold": threshold,
        "curve": [asdict(p) for p in curve],
        "val": tuning,
        "test": log.summary(),
        "examples": list(examples),
        "ablation": _ablation(stage, twins),
        "groups": twins["groups"],
        "attributes": twins["attributes"],
        "seconds": seconds,
    }


def _pct(value: object) -> str:
    return f"{float(cast(float, value)) * 100:.1f}"


def _row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _ablation_lines(rows: Sequence[Mapping[str, object]]) -> list[str]:
    keys = (*ABLATION_KEYS, "macro_f1", "weighted_f1", "recall_over_ceiling")
    titles = ("P", "R", "F1", "покрытие", "macro F1", "F1 взвеш.", "R сверх потолка")
    lines = [_row(["срез", "ступень", *titles]), _row(["---"] * (len(keys) + 2))]
    for row in rows:
        for stage in ("ranker", "twins"):
            values = cast(Mapping[str, float], row[stage])
            label = "ранжировщик" if stage == "ranker" else "+ двойники"
            lines.append(_row([str(row["group"]), label, *[_pct(values[k]) for k in keys]]))
    return lines


def render_twin_markdown(report: Mapping[str, object]) -> str:
    val = cast(Mapping[str, object], report["val"])
    test = cast(Mapping[str, object], report["test"])
    lines = [
        "# Отчёт метрик: двойники в каталоге",
        "",
        (f"Карточек: {report['cards']}; индекс train: {report['index_entries']}; порог сходства "
         f"{report['threshold']} (выбран на val). Файл генерируется командой `uv run twins` и руками "
         "не правится."),
        "", "## Абляция «ранжировщик → + двойники»", "", *_ablation_lines(
            cast(Sequence[Mapping[str, object]], report["ablation"])),
        "", "## Двойники на val (порог, ложные двойники)", "",
        _row(["показатель", "значение"]), _row(["---", "---"]),
        *[_row([k, str(v)]) for k, v in val.items()],
        "", "## Переносы на test + new_category", "",
        _row(["показатель", "значение"]), _row(["---", "---"]),
        *[_row([k, str(v)]) for k, v in test.items()],
        "", "## Кривая порога на val", "", _row(["порог", "P", "R", "F1", "переносов"]),
        _row(["---"] * 5),
        *[_row([str(p["threshold"]), _pct(p["precision"]), _pct(p["recall"]), _pct(p["f1"]),
                str(p["transfers"])])
          for p in cast(Sequence[Mapping[str, float]], report["curve"])],
        "", "## Примеры ошибок переноса на val", "",
        _row(["SKU", "название", "атрибут", "эталон", "двойник", "SKU двойника", "сходство"]),
        _row(["---"] * 7),
        *[_row([str(e["sku_id"]), str(e["title"]).replace("|", "/"), str(e["attribute"]),
                str(e["gold"]), str(e["twin_value"]), str(e["twin_sku"]), str(e["similarity"])])
          for e in cast(Sequence[Mapping[str, object]], report["examples"])],
        "",
    ]
    detail = render_markdown({"cards": report["cards"], "lexicon_entries": 0,
                              "groups": report["groups"], "attributes": report["attributes"]})
    body = detail.split("## Сводка по срезам", 1)[1]
    return "\n".join(lines) + "\n## Сводка по срезам (ранжировщик + двойники)" + body
