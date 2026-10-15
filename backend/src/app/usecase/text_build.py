from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from app.domain.card_text import clean_text
from app.domain.category_metrics import pick_threshold, top_k_accuracy
from app.domain.page_text import clean_page
from app.domain.text_reading import rank_categories
from app.usecase.interface import Embeddings, Logger
from app.usecase.ranker_ports import Calibrator
from app.usecase.text_ports import CatalogEntry, CatalogSearch, TextCorpus, TextIndexSink
from app.usecase.text_sample import attach_gold, gold_display, sample_cards, synthetic_inputs

TRAIN = "train"
VAL = "val"
EMBED_CHUNK = 1000
SEARCH_CHUNK = 32


@dataclass(frozen=True, slots=True)
class TextIndexConfig:
    per_category: int = 40
    neighbors: int = 20
    val_cards: int = 300
    target_precision: float = 0.9
    query_chars: int = 2000
    seed: int = 0


class BuildTextIndex:
    def __init__(self, corpus: TextCorpus, sink: TextIndexSink, logger: Logger) -> None:
        self._corpus = corpus
        self._sink = sink
        self._logger = logger

    async def build(self, config: TextIndexConfig, names: Mapping[int, str],
                    embeddings: Embeddings, embedding_model: str, dimensions: int) -> int:
        required = self._corpus.required()
        categories = frozenset(r.category_id for r in required)
        cards = sample_cards(self._corpus, TRAIN, categories, config.per_category,
                             len(categories) * config.per_category, config.seed)
        attributes = frozenset(r.attribute for r in required)
        sampled = attach_gold(self._corpus, cards, frozenset({TRAIN}), attributes)
        entries = [CatalogEntry(s.card.sku_id, s.card.category_id or 0,
                                clean_text(s.card.title), gold_display(s.gold)) for s in sampled]
        self._logger.info("text_index_entries", entries=len(entries), categories=len(categories))
        self._sink.start(entries, names, embedding_model, dimensions)
        for start in range(0, len(entries), EMBED_CHUNK):
            chunk = entries[start:start + EMBED_CHUNK]
            self._sink.add_vectors(await embeddings.embed_documents([e.title for e in chunk]))
            self._logger.info("text_index_embedded", done=start + len(chunk))
        self._sink.finish()
        return len(entries)

    async def calibrate(self, config: TextIndexConfig, entries: Sequence[CatalogEntry],
                        search: CatalogSearch, calibrator: Calibrator) -> dict[str, object]:
        categories = frozenset(e.category_id for e in entries)
        cards = sample_cards(self._corpus, VAL, categories, 1, config.val_cards, config.seed)
        inputs = synthetic_inputs(attach_gold(self._corpus, cards, frozenset({VAL}),
                                              frozenset()), config.seed)
        truth: list[int] = []
        ranked: list[list[tuple[int, float]]] = []
        for start in range(0, len(inputs), SEARCH_CHUNK):
            chunk = inputs[start:start + SEARCH_CHUNK]
            texts = [_query(raw, config.query_chars) for _, _, raw in chunk]
            for (sampled, _, _), hits in zip(chunk, await search.search(texts, config.neighbors),
                                             strict=True):
                truth.append(sampled.card.category_id or 0)
                ranked.append(rank_categories([(entries[i].category_id, s) for i, s in hits],
                                              3))
        tops = [r[0][1] if r else 0.0 for r in ranked]
        calibrator.fit(tops, [bool(r) and r[0][0] == t for t, r in zip(truth, ranked,
                                                                        strict=True)])
        calibrated = _calibrated(ranked, calibrator.transform)
        threshold = pick_threshold(truth, calibrated, config.target_precision)
        accepted = [(t, r[0][0]) for t, r in zip(truth, calibrated, strict=True)
                    if r and r[0][1] >= threshold]
        report: dict[str, object] = {
            "val_inputs": len(truth),
            "top1": round(top_k_accuracy(truth, ranked, 1), 4),
            "top3": round(top_k_accuracy(truth, ranked, 3), 4),
            "threshold": threshold,
            "coverage": round(len(accepted) / len(truth), 4) if truth else 0.0,
            "precision": round(sum(1 for t, p in accepted if t == p) / len(accepted), 4)
            if accepted else 0.0,
        }
        self._logger.info("text_index_calibrated", kind=search.kind, threshold=threshold,
                          coverage=float(str(report["coverage"])))
        self._sink.save_model(search.kind, calibrator, threshold, report)
        return report


def _query(raw: str, chars: int) -> str:
    return clean_page(raw).text[:chars]


def _calibrated(ranked: Sequence[Sequence[tuple[int, float]]],
                transform: Callable[[Sequence[float]], Sequence[float]]
                ) -> list[list[tuple[int, float]]]:
    result = []
    for r in ranked:
        values = transform([s for _, s in r]) if r else []
        result.append([(c, float(v)) for (c, _), v in zip(r, values, strict=True)])
    return result
