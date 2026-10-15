from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.candidate import Candidate
from app.domain.scoring import Pick
from app.domain.twin import (
    TWIN_SOURCE,
    TwinEntry,
    TwinQuery,
    TwinValue,
    accepted,
    title_numbers,
    twin_title,
    vote,
)
from app.usecase.extraction import CardExtraction
from app.usecase.ranker_ports import Calibrator
from app.usecase.stand_ports import StandTwin
from app.usecase.twin_ports import TitleIndex


@dataclass(frozen=True, slots=True)
class TwinSettings:
    threshold: float
    floor: float = 0.5
    k: int = 10


def twin_entry(twin: StandTwin) -> TwinEntry:
    values = {a: TwinValue(k, v) for a, (k, v) in twin.values.items()}
    return TwinEntry(twin.sku_id, twin.title, title_numbers(twin.title), twin.brand, twin.model,
                     values)


class StandTwins:
    def __init__(self, twins: Sequence[StandTwin], index: TitleIndex, calibrator: Calibrator,
                 settings: TwinSettings) -> None:
        self._entries = [twin_entry(t) for t in twins]
        self._titles = {e.sku_id: e.title for e in self._entries}
        self._index = index
        self._calibrator = calibrator
        self._settings = settings
        index.fit([e.title for e in self._entries])

    def picks(self, extraction: CardExtraction, slots: Sequence[str],
              brand: Pick | None) -> dict[str, Pick]:
        title = twin_title(extraction.text.text[: extraction.text.title_end])
        if not title or not slots or not self._entries:
            return {}
        query = TwinQuery(title, title_numbers(title), brand.candidate.key if brand else None)
        hits = self._index.neighbors([title], self._settings.k)[0]
        near = [(self._entries[i], s) for i, s in hits]
        kept = accepted(vote(query, near, slots, self._settings.floor), self._settings.threshold)
        if not kept:
            return {}
        confidences = self._calibrator.transform([t.similarity for t in kept.values()])
        picks = {}
        for (name, transfer), confidence in zip(kept.items(), confidences, strict=True):
            evidence = f"SKU {transfer.twin_sku}: {self._titles.get(transfer.twin_sku, '')}"
            candidate = Candidate(name, transfer.key, transfer.value, evidence, -1, -1,
                                  TWIN_SOURCE, "twin", round(transfer.similarity, 4), 0.0, 0)
            picks[name] = Pick(candidate, round(float(confidence), 4), (TWIN_SOURCE,))
        return picks
