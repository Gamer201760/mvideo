import asyncio
import time
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.domain.card_text import clean_text
from app.domain.category_metrics import macro_f1, top_k_accuracy
from app.domain.metrics import MetricsBook, Observation
from app.domain.page_text import QUOTE_SPACE
from app.domain.profile import AttributeProfile
from app.domain.values import canonical_key
from app.usecase.extract_card import ExtractCard
from app.usecase.interface import Logger
from app.usecase.stand_ports import CardInput, StandPack
from app.usecase.text_extract import ExtractText, TextResult
from app.usecase.text_ports import Spending, TextCorpus
from app.usecase.text_sample import SampledCard, attach_gold, sample_cards, synthetic_inputs

TEST = "test"
NEW = "new_category"
STRUCTURED = "structured"
FUZZY_TITLE = 0.8
MILLION = 1_000_000


@dataclass(frozen=True, slots=True)
class TextEvalConfig:
    test_cards: int = 150
    new_cards: int = 50
    seed: int = 0
    budget_rub: float = 30.0
    concurrency: int = 6


@dataclass(slots=True)
class KindStats:
    truth: list[int] = field(default_factory=list)
    ranked: list[list[tuple[int, float]]] = field(default_factory=list)
    accepted: list[int | None] = field(default_factory=list)
    rejected_new: list[bool] = field(default_factory=list)
    title_exact: list[bool] = field(default_factory=list)
    title_ratio: list[float] = field(default_factory=list)
    title_llm: int = 0
    values: int = 0
    quoted: int = 0
    seconds: list[float] = field(default_factory=list)


class EvaluateText:
    def __init__(self, corpus: TextCorpus, extract: ExtractText, structured: ExtractCard,
                 pack: StandPack, spending: Sequence[Spending], logger: Logger) -> None:
        self._corpus = corpus
        self._extract = extract
        self._structured = structured
        self._pack = pack
        self._spending = spending
        self._logger = logger

    async def run(self, config: TextEvalConfig) -> dict[str, object]:
        categories = frozenset(c.category_id for c in self._pack.categories)
        attributes = frozenset(r.attribute for r in self._pack.required)
        test = sample_cards(self._corpus, TEST, categories, config.test_cards, config.test_cards,
                            config.seed)
        new = sample_cards(self._corpus, NEW, None, config.new_cards, config.new_cards,
                           config.seed)
        cards = attach_gold(self._corpus, [*test, *new], frozenset({TEST, NEW}), attributes)
        inputs = synthetic_inputs(cards, config.seed)
        book = MetricsBook(weighted=False)
        stats: dict[str, KindStats] = defaultdict(KindStats)
        processed = 0
        stopped = False
        for start in range(0, len(inputs), config.concurrency):
            if self.spent() >= config.budget_rub:
                stopped = True
                self._logger.warning("text_eval_budget_reached", spent=self.spent())
                break
            chunk = inputs[start:start + config.concurrency]
            results = await asyncio.gather(*(self._timed(raw) for _, _, raw in chunk))
            for (sampled, kind, _), (result, seconds) in zip(chunk, results, strict=True):
                self._observe(stats[kind], book, kind, sampled, result, seconds)
            processed += len(chunk)
            if processed % 60 == 0:
                self._logger.info("text_eval_progress", inputs=processed, spent=self.spent())
        for sampled in cards:
            if sampled.card.split == TEST:
                await self._observe_structured(book, sampled)
        spent = self.spent()
        return {
            "config": {"test_cards": len(test), "new_category_cards": len(new),
                       "seed": config.seed, "budget_rub": config.budget_rub},
            "inputs": processed,
            "stopped_by_budget": stopped,
            "kinds": {k: _kind_report(s, book, k) for k, s in stats.items()},
            "structured": book.micro(STRUCTURED),
            "structured_macro_f1": book.macro_f1(STRUCTURED),
            "cost": {"spent_rub": round(spent, 4),
                     "paid_calls": sum(s.paid_calls() for s in self._spending),
                     "per_input_rub": round(self.per_input(), 6),
                     "per_million_rub": round(self.per_input() * MILLION, 0)},
        }

    async def _timed(self, raw: str) -> tuple[TextResult, float]:
        started = time.monotonic()
        result = await self._extract.execute(raw)
        return result, time.monotonic() - started

    def per_input(self) -> float:
        return sum(s.spent_rub() / s.paid_calls() for s in self._spending if s.paid_calls())

    def spent(self) -> float:
        return sum(s.spent_rub() for s in self._spending)

    def _observe(self, stats: KindStats, book: MetricsBook, kind: str, sampled: SampledCard,
                 result: TextResult, seconds: float) -> None:
        card = sampled.card
        stats.seconds.append(seconds)
        stats.values += len(result.values)
        stats.quoted += sum(1 for v in result.values if v.start >= 0)
        stats.title_llm += 1 if result.title_source == "llm" else 0
        title = _norm(card.title or "")
        found = _norm(result.title or "")
        stats.title_exact.append(bool(found) and found == title)
        stats.title_ratio.append(SequenceMatcher(None, found, title).ratio() if found else 0.0)
        if card.split == NEW:
            stats.rejected_new.append(result.category_id is None)
            return
        truth = card.category_id or 0
        stats.truth.append(truth)
        stats.ranked.append(list(result.candidates))
        stats.accepted.append(result.category_id)
        predicted = {v.attribute: v for v in result.values if not v.in_review}
        for name, profile in self._profiles(truth).items():
            value = predicted.get(name)
            key = (value.key or canonical_key(value.value, None, profile.numeric)) \
                if value else None
            _add(book, kind, name, profile, sampled, key)

    async def _observe_structured(self, book: MetricsBook, sampled: SampledCard) -> None:
        card = sampled.card
        result = await self._structured.execute(CardInput(
            title=card.title or "", description=card.description or "",
            seller_params=card.seller_params, category_id=card.category_id))
        predicted = {v.attribute: v for v in result.values if not v.in_review}
        for name, profile in self._profiles(card.category_id or 0).items():
            value = predicted.get(name)
            _add(book, STRUCTURED, name, profile, sampled, value.key if value else None)

    def _profiles(self, category: int) -> dict[str, AttributeProfile]:
        return {r.attribute: self._pack.profiles[r.attribute] for r in self._pack.required
                if r.category_id == category and r.attribute in self._pack.profiles}


def _add(book: MetricsBook, group: str, name: str, profile: AttributeProfile,
         sampled: SampledCard, key: str | None) -> None:
    truth = sampled.gold.get(name)
    correct = truth is not None and key is not None and \
        key == canonical_key(truth[0], truth[1], profile.numeric)
    book.add([group], Observation(name, truth is not None, key is not None, correct, False,
                                  False))


def _norm(text: str) -> str:
    return QUOTE_SPACE.sub(" ", clean_text(text).casefold().replace("ё", "е")).strip()


def _kind_report(stats: KindStats, book: MetricsBook, kind: str) -> dict[str, object]:
    truth, ranked = stats.truth, stats.ranked
    accepted = [(t, a) for t, a in zip(truth, stats.accepted, strict=True) if a is not None]
    seconds = sorted(stats.seconds)
    return {
        "inputs": len(stats.seconds),
        "category": {
            "cards": len(truth),
            "top1": _round(top_k_accuracy(truth, ranked, 1)),
            "top3": _round(top_k_accuracy(truth, ranked, 3)),
            "macro_f1": _round(macro_f1(truth, [r[0][0] if r else -1 for r in ranked])),
            "coverage": _ratio(len(accepted), len(truth)),
            "precision": _ratio(sum(1 for t, a in accepted if t == a), len(accepted)),
            "new_category_cards": len(stats.rejected_new),
            "new_category_rejected": _ratio(sum(stats.rejected_new), len(stats.rejected_new)),
        },
        "title": {
            "exact": _ratio(sum(stats.title_exact), len(stats.title_exact)),
            "fuzzy": _ratio(sum(1 for r in stats.title_ratio if r >= FUZZY_TITLE),
                            len(stats.title_ratio)),
            "mean_ratio": _ratio(sum(stats.title_ratio), len(stats.title_ratio)),
            "from_llm": _ratio(stats.title_llm, len(stats.seconds)),
        },
        "attributes": book.micro(kind),
        "attributes_macro_f1": book.macro_f1(kind),
        "quoted_share": _ratio(stats.quoted, stats.values),
        "seconds": {"mean": _ratio(sum(seconds), len(seconds)),
                    "p95": round(seconds[int(0.95 * (len(seconds) - 1))], 3) if seconds else 0.0},
    }


def _ratio(part: float, whole: float) -> float:
    return round(part / whole, 4) if whole else 0.0


def _round(value: float) -> float:
    return round(value, 4)
