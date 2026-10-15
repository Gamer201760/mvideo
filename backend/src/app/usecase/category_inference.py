import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass

from app.domain.category_guess import ClickMapping, Ranked, majority_mapping
from app.domain.category_metrics import (
    acceptance,
    curve,
    histogram,
    macro_f1,
    pick_threshold,
    rejection_threshold,
    top_k_accuracy,
)
from app.usecase.category_ports import (
    CategoryCard,
    CategoryClassifier,
    CategoryCorpus,
    CategorySink,
    ClickVote,
)
from app.usecase.category_report import render_markdown
from app.usecase.category_scan import scan_cards
from app.usecase.interface import Logger

ALL_SPLITS = frozenset({"train", "val", "test", "new_category"})


@dataclass(frozen=True, slots=True)
class CategoryConfig:
    target_precision: float = 0.9
    ood_reject_share: float = 0.8
    top_k: int = 3
    batch: int = 20_000
    samples: int = 20
    seed: int = 0


class InferCategories:
    def __init__(
        self,
        corpus: CategoryCorpus,
        classifier: CategoryClassifier,
        sink: CategorySink,
        logger: Logger,
    ) -> None:
        self._corpus = corpus
        self._classifier = classifier
        self._sink = sink
        self._logger = logger

    def run(self, config: CategoryConfig) -> dict[str, object]:
        started = time.perf_counter()
        required = self._corpus.required_categories()
        labelled = list(self._corpus.labelled(ALL_SPLITS))
        known = {name: [c for c in labelled if c.split == name
                        and c.catalog_category in required] for name in ("train", "val", "test")}
        unseen = [c for c in labelled if c.split == "new_category"]
        train = known["train"]
        self._logger.info("category_fit", cards=len(train), categories=len(required))
        self._classifier.fit([c.text for c in train], [_label(c) for c in train])
        threshold, selection = self._threshold(known["val"], unseen, config)
        classifier_report = self._evaluate(known["test"], threshold, config)
        top_votes = _top_votes(self._corpus.click_votes())
        clicks_report, mapping = self._click_mapping(labelled, top_votes)
        scan = scan_cards(self._corpus, self._classifier, self._sink, self._logger, top_votes,
                          mapping, threshold, config.batch, config.top_k, config.samples,
                          config.seed)
        report: dict[str, object] = {
            "required_categories": len(required),
            "train_cards": len(train),
            "target_precision": config.target_precision,
            "ood_reject_share": config.ood_reject_share,
            "threshold": threshold,
            "threshold_selection": selection,
            "classifier_test": classifier_report,
            "clicks": clicks_report,
            "coverage": scan.summary(),
            "seconds": round(time.perf_counter() - started, 1),
        }
        self._sink.report(report, render_markdown(report))
        return report

    def _threshold(
        self, val: Sequence[CategoryCard], unseen: Sequence[CategoryCard], config: CategoryConfig
    ) -> tuple[float, dict[str, object]]:
        val_ranked = self._classifier.rank([c.text for c in val], config.top_k)
        val_top = _tops(val_ranked)
        unseen_top = _tops(self._classifier.rank([c.text for c in unseen], config.top_k))
        by_precision = pick_threshold([_label(c) for c in val], val_ranked,
                                      config.target_precision)
        by_ood = rejection_threshold(unseen_top, config.ood_reject_share)
        threshold = max(by_precision, by_ood)
        accepted = [(_label(c), r[0][0]) for c, r in zip(val, val_ranked, strict=True)
                    if r and r[0][1] >= threshold]
        selection: dict[str, object] = {
            "by_val_precision": by_precision,
            "by_new_category_rejection": by_ood,
            "val_cards": len(val),
            "new_category_cards": len(unseen),
            "val_coverage": round(acceptance(val_top, threshold), 4),
            "val_precision": round(sum(1 for t, p in accepted if t == p) / len(accepted), 4)
            if accepted else 0.0,
            "new_category_rejected": round(1 - acceptance(unseen_top, threshold), 4),
            "val_histogram": histogram(val_top),
            "new_category_histogram": histogram(unseen_top),
        }
        self._logger.info("category_threshold", threshold=threshold, by_precision=by_precision,
                          by_ood=by_ood)
        return threshold, selection

    def _evaluate(
        self, test: Sequence[CategoryCard], threshold: float, config: CategoryConfig
    ) -> dict[str, object]:
        truth = [_label(c) for c in test]
        ranked = self._classifier.rank([c.text for c in test], config.top_k)
        accepted = [(t, r[0][0]) for t, r in zip(truth, ranked, strict=True)
                    if r and r[0][1] >= threshold]
        return {
            "cards": len(test),
            "top1": round(top_k_accuracy(truth, ranked, 1), 4),
            "top3": round(top_k_accuracy(truth, ranked, 3), 4),
            "macro_f1": round(macro_f1(truth, [r[0][0] if r else -1 for r in ranked]), 4),
            "coverage_at_threshold": round(len(accepted) / len(test), 4) if test else 0.0,
            "precision_at_threshold": round(
                sum(1 for t, p in accepted if t == p) / len(accepted), 4) if accepted else 0.0,
            "curve": [asdict(p) for p in curve(truth, ranked)],
        }

    def _click_mapping(
        self, labelled: Sequence[CategoryCard], votes: Mapping[int, ClickVote]
    ) -> tuple[dict[str, object], dict[int, ClickMapping]]:
        catalog = {c.sku_id: _label(c) for c in labelled}
        split = {c.sku_id: c.split for c in labelled}
        held_out = majority_mapping((v.click_category, catalog[s], v.clicks)
                                    for s, v in votes.items() if split.get(s) == "train")
        test = [(v.click_category, catalog[s]) for s, v in votes.items()
                if split.get(s) == "test"]
        hits = sum(1 for click, true in test if click in held_out
                   and held_out[click].category_id == true)
        mapped = sum(1 for click, _ in test if click in held_out)
        mapping = majority_mapping((v.click_category, catalog[s], v.clicks)
                                   for s, v in votes.items() if s in catalog)
        report: dict[str, object] = {
            "test_cards": len(test),
            "test_mapped": mapped,
            "test_accuracy": round(hits / mapped, 4) if mapped else 0.0,
            "direct_id_match": round(
                sum(1 for click, true in test if click == true) / len(test), 4) if test else 0.0,
            "click_categories": len(mapping),
        }
        return report, mapping


def _tops(ranked: Sequence[Ranked]) -> list[float]:
    return [r[0][1] for r in ranked if r]


def _label(card: CategoryCard) -> int:
    if card.catalog_category is None:
        raise ValueError(f"card {card.sku_id} has no catalog category")
    return card.catalog_category


def _top_votes(votes: Iterable[ClickVote]) -> dict[int, ClickVote]:
    best: dict[int, ClickVote] = {}
    for vote in votes:
        current = best.get(vote.sku_id)
        if current is None or vote.clicks > current.clicks:
            best[vote.sku_id] = vote
    return best
