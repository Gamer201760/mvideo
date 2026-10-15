from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

from app.domain.calibration import expected_calibration_error, reliability
from app.domain.metrics import MetricsBook
from app.usecase.decision_stage import StageResult
from app.usecase.report import build_report, render_markdown


@dataclass(frozen=True, slots=True)
class ReportMeta:
    provider: str
    offline: bool
    sample: Mapping[str, object]
    stage_config: Mapping[str, object]
    price_input_per_mtok: float | None = None
    price_output_per_mtok: float | None = None

CARDS_PER_MILLION = 1_000_000
BUDGET_SKIP = "budget exhausted"
COMPARE_GROUPS = ("all", "split:test", "split:new_category", "split:val", "categories:head",
                  "categories:tail", "category:smartphones", "category:laptops")


@dataclass(slots=True)
class CalibrationBook:
    confidences: list[float] = field(default_factory=list)
    correct: list[bool] = field(default_factory=list)

    def extend(self, pairs: Iterable[tuple[float, bool]]) -> None:
        for confidence, hit in pairs:
            self.confidences.append(confidence)
            self.correct.append(hit)

    def summary(self) -> dict[str, object]:
        table = reliability(self.confidences, self.correct)
        return {
            "pairs": len(self.confidences),
            "ece": round(expected_calibration_error(table), 4),
            "bins": [{"low": round(b.low, 3), "high": round(b.high, 3), "count": b.count,
                      "mean_confidence": round(b.confidence, 4), "accuracy": round(b.accuracy, 4)}
                     for b in table if b.count],
        }


@dataclass(slots=True)
class UsageBook:
    cards: int = 0
    calls: int = 0
    cached: int = 0
    skipped: int = 0
    failures: int = 0
    budget_skips: int = 0
    questions: int = 0
    dictionary_questions: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    priced_calls: int = 0
    latencies: list[int] = field(default_factory=list)
    models: set[str] = field(default_factory=set)

    def add(self, result: StageResult | None, failure: str | None) -> None:
        self.cards += 1
        if failure == BUDGET_SKIP:
            self.budget_skips += 1
            return
        if failure is not None:
            self.failures += 1
            return
        if result is None or result.usage is None:
            self.skipped += 1
            return
        self.questions += result.questions
        self.dictionary_questions += result.dictionary_questions
        usage = result.usage
        self.models.add(usage.model)
        self.input_tokens += usage.input_tokens or 0
        self.output_tokens += usage.output_tokens or 0
        if usage.cost_usd is not None:
            self.cost_usd += usage.cost_usd
            self.priced_calls += 1
        if result.cached:
            self.cached += 1
        else:
            self.calls += 1
            self.latencies.append(usage.duration_ms)

    def summary(self, price_in: float | None, price_out: float | None) -> dict[str, object]:
        answered = self.cards - self.failures - self.skipped - self.budget_skips
        ordered = sorted(self.latencies)
        p50 = ordered[len(ordered) // 2] if ordered else None
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] if ordered else None
        per_card_in = self.input_tokens / answered if answered else 0.0
        per_card_out = self.output_tokens / answered if answered else 0.0
        return {
            "cards": self.cards,
            "decided_cards": answered,
            "live_calls": self.calls,
            "cache_hits": self.cached,
            "cards_without_questions": self.skipped,
            "failures": self.failures,
            "budget_skips": self.budget_skips,
            "questions_per_card": round(self.questions / answered, 2) if answered else 0.0,
            "dictionary_questions": self.dictionary_questions,
            "latency_ms_p50": p50,
            "latency_ms_p95": p95,
            "input_tokens_per_card": round(per_card_in, 1),
            "output_tokens_per_card": round(per_card_out, 1),
            "models": sorted(self.models),
            "cost_usd_total": round(self.cost_usd, 6),
            "cost_usd_per_million_cards": self.per_million(price_in, price_out, answered),
        }

    def per_million(
        self, price_in: float | None, price_out: float | None, answered: int
    ) -> float | None:
        if self.priced_calls:
            return round(self.cost_usd / self.priced_calls * CARDS_PER_MILLION, 2)
        if price_in is None or price_out is None or not answered:
            return None
        per_card = (self.input_tokens * price_in + self.output_tokens * price_out) / 1e6 / answered
        return round(per_card * CARDS_PER_MILLION, 2)


def _compare(books: MetricsBook, baseline: MetricsBook) -> dict[str, object]:
    return {
        group: {"decision": books.micro(group), "baseline": baseline.micro(group)}
        for group in COMPARE_GROUPS if group in books.groups
    }


def build_decision_report(
    books: tuple[MetricsBook, MetricsBook], baseline: tuple[MetricsBook, MetricsBook],
    calibration: CalibrationBook, usage: UsageBook, *, meta: ReportMeta, cards: int,
    lexicon_entries: int, attributes: int, seconds: float,
    grid: Sequence[Mapping[str, object]] = (), slots: Mapping[str, object] | None = None,
) -> dict[str, object]:
    report = build_report(books[0], books[1], cards=cards, lexicon_entries=lexicon_entries,
                          attributes=attributes)
    report["stage"] = f"decision model ({meta.provider}) over rule candidates"
    report["confidence_calibrated"] = False
    report["offline_stub"] = meta.offline
    report["sample"] = dict(meta.sample)
    report["stage_config"] = dict(meta.stage_config)
    report["usage"] = usage.summary(meta.price_input_per_mtok, meta.price_output_per_mtok)
    report["calibration"] = calibration.summary()
    report["baseline_same_sample"] = _compare(books[0], baseline[0])
    report["baseline_same_sample_weighted"] = _compare(books[1], baseline[1])
    report["override_grid"] = [dict(row) for row in grid]
    report["routing"] = dict(slots or {})
    report["seconds"] = seconds
    return report


def _pct(value: object) -> str:
    return f"{float(cast(float, value)) * 100:.1f}"


def render_decision_markdown(report: Mapping[str, object]) -> str:
    body = render_markdown(report).split("\n", 1)[1]
    usage = cast(Mapping[str, object], report["usage"])
    calibration = cast(Mapping[str, object], report["calibration"])
    lines = [f"# Отчёт метрик: {report['stage']}", ""]
    if report.get("offline_stub"):
        lines += ["> Офлайн-заглушка `lexical`: это проверка пайплайна, а не качество продукта.", ""]
    lines += ["## Сравнение с базлайном на той же выборке", "",
              "| срез | F1 базлайн | F1 decision | P базлайн | P decision | R базлайн | R decision |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    compare = cast(Mapping[str, Mapping[str, Mapping[str, float]]], report["baseline_same_sample"])
    for group, pair in compare.items():
        b, d = pair["baseline"], pair["decision"]
        lines.append(f"| {group} | {_pct(b['f1'])} | {_pct(d['f1'])} | {_pct(b['precision'])} | "
                     f"{_pct(d['precision'])} | {_pct(b['recall'])} | {_pct(d['recall'])} |")
    lines += ["", "## Калибровка вероятностей", "",
              f"Пар с эталоном: {calibration['pairs']}; ECE: {calibration['ece']}.", "",
              "| корзина | пар | средняя уверенность | точность |", "| --- | --- | --- | --- |"]
    for b in cast(list[Mapping[str, float]], calibration["bins"]):
        lines.append(f"| {b['low']:.1f}–{b['high']:.1f} | {int(b['count'])} | "
                     f"{b['mean_confidence']:.3f} | {b['accuracy']:.3f} |")
    routing = cast(Mapping[str, object], report.get("routing", {}))
    lines += ["", "## Слоты, отправленные в decision-модель", ""]
    lines += [f"- {k}: {v}" for k, v in routing.items() if k != "attributes"]
    lines += ["", "| атрибут | слотов с эталоном | базлайн верно | decision верно | decision ответил |",
              "| --- | --- | --- | --- | --- |"]
    for name, counts in cast(Mapping[str, Mapping[str, int]], routing.get("attributes", {})).items():
        lines.append(f"| {name} | {counts['slots']} | {counts['baseline_correct']} | "
                     f"{counts['decision_correct']} | {counts['decision_answered']} |")
    lines += ["", "## Порог переопределения базлайна", "",
              "| порог | снять при «не указано» ≥ | P | R | F1 | покрытие | F1 взвеш. | macro F1 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in cast(list[Mapping[str, float]], report.get("override_grid", [])):
        drop = "—" if row.get("drop") is None else row["drop"]
        lines.append(f"| {row['override']} | {drop} | {_pct(row['precision'])} | {_pct(row['recall'])} | "
                     f"{_pct(row['f1'])} | {_pct(row['coverage_after'])} | "
                     f"{_pct(row['weighted_f1'])} | {_pct(row['macro_f1'])} |")
    lines += ["", "## Вызовы и стоимость", ""]
    lines += [f"- {key}: {value}" for key, value in usage.items()]
    lines += ["", body]
    return "\n".join(lines)
