from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.card_text import clean_text
from app.domain.inference import Usage
from app.domain.page_text import PageText, clean_page, find_quote
from app.domain.review import UnknownCategory
from app.domain.text_reading import EmptyText, TextIndexMissing, rank_categories
from app.usecase.extract_card import CardResult, ExtractCard, ExtractedValue
from app.usecase.interface import LanguageModel
from app.usecase.stand_ports import CardInput
from app.usecase.text_ports import CatalogEntry, CatalogSearch, TextIndex
from app.usecase.text_title import TitleRead, TitleReader

NEIGHBOR_SOURCE = "neighbor"
TWIN_START = -1


@dataclass(frozen=True, slots=True)
class TextSettings:
    neighbors: int = 20
    candidates: int = 3
    references: int = 5
    query_chars: int = 2000
    hint_threshold: float = 0.5


@dataclass(frozen=True, slots=True, kw_only=True)
class TextValue:
    attribute: str
    value: str
    key: str
    confidence: float
    source: str
    sources: tuple[str, ...]
    evidence: str
    start: int
    end: int
    text_start: int
    text_end: int
    in_review: bool
    review_id: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class TextResult:
    text: str
    category_id: int | None
    category_name: str | None
    category_confidence: float
    candidates: tuple[tuple[int, float], ...]
    title: str | None
    title_source: str | None
    title_start: int
    title_end: int
    values: tuple[TextValue, ...]
    missing: tuple[str, ...]
    threshold: float
    search: str
    usage: Usage | None


class ExtractText:
    def __init__(self, index: TextIndex | None, search: CatalogSearch | None, cards: ExtractCard,
                 language: LanguageModel | None, settings: TextSettings | None = None) -> None:
        self._index = index
        self._search = search
        self._cards = cards
        self._titles = TitleReader(language)
        self._settings = settings or TextSettings()

    async def execute(self, raw: str) -> TextResult:
        index, search = self._require()
        page = clean_page(raw)
        if not page.text:
            raise EmptyText()
        settings = self._settings
        hits = (await search.search([page.text[: settings.query_chars]], settings.neighbors))[0]
        near = [(index.entries[i], s) for i, s in hits]
        ranked = rank_categories([(e.category_id, s) for e, s in near], settings.candidates)
        model = index.models[search.kind]
        confidences = model.calibrator.transform([share for _, share in ranked])
        candidates = tuple((c, round(float(p), 4))
                           for (c, _), p in zip(ranked, confidences, strict=True))
        category = candidates[0][0] if candidates and candidates[0][1] >= model.threshold \
            else None
        references = [e.title for e, _ in near if category is None or e.category_id == category]
        title = await self._titles.read(page.text, references[: settings.references])
        card, result = await self._extract(page, title, category)
        values = [v for v in (_quoted(page, card, value, title) for value in result.values)
                  if v is not None]
        found = {v.attribute for v in values}
        hints = _hints(page, [(e, s) for e, s in near if e.category_id == category],
                       [m for m in result.missing if m not in found],
                       max(settings.hint_threshold, result.threshold))
        values.extend(hints)
        found |= {v.attribute for v in hints}
        missing = sorted({*result.missing, *(v.attribute for v in result.values)} - found)
        return TextResult(
            text=page.text, category_id=category,
            category_name=index.names.get(category) if category is not None else None,
            category_confidence=candidates[0][1] if candidates else 0.0,
            candidates=candidates,
            title=page.text[title.start:title.end] if title else None,
            title_source=title.source if title else None,
            title_start=page.source_span(title.start, title.end)[0] if title else -1,
            title_end=page.source_span(title.start, title.end)[1] if title else -1,
            values=tuple(sorted(values, key=lambda v: v.attribute)), missing=tuple(missing),
            threshold=result.threshold, search=search.kind,
            usage=title.usage if title else None,
        )

    def category_names(self) -> Mapping[int, str]:
        return self._index.names if self._index is not None else {}

    def _require(self) -> tuple[TextIndex, CatalogSearch]:
        if self._index is None or self._search is None:
            raise TextIndexMissing()
        return self._index, self._search

    async def _extract(self, page: PageText, title: TitleRead | None,
                       category: int | None) -> tuple[CardInput, CardResult]:
        head = page.text[title.start:title.end] if title else ""
        card = CardInput(title=head, description=page.text, seller_params=(),
                         category_id=category)
        try:
            return card, await self._cards.execute(card)
        except UnknownCategory:
            card = CardInput(title=head, description=page.text, seller_params=(),
                             category_id=None)
            return card, await self._cards.execute(card)


def _quoted(page: PageText, card: CardInput, value: ExtractedValue,
            title: TitleRead | None) -> TextValue | None:
    if value.start == TWIN_START:
        return _value(value, value.evidence, TWIN_START, TWIN_START, TWIN_START, TWIN_START)
    span = _in_page(page, card, value, title)
    if span is None:
        return None
    start, end = page.source_span(*span)
    return _value(value, page.text[span[0]:span[1]], start, end, *span)


def _in_page(page: PageText, card: CardInput, value: ExtractedValue,
             title: TitleRead | None) -> tuple[int, int] | None:
    head = clean_text(card.title)
    body = len(head) + 1
    wanted = value.evidence.casefold()
    if title is not None and value.end <= len(head):
        span = (title.start + value.start, title.start + value.end)
    elif clean_text(card.description) == page.text and value.start >= body:
        span = (value.start - body, value.end - body)
    else:
        span = (0, 0)
    if 0 <= span[0] < span[1] <= len(page.text) and \
            page.text[span[0]:span[1]].casefold() == wanted:
        return span
    return find_quote(page.text, value.evidence)


def _value(value: ExtractedValue, evidence: str, start: int, end: int, text_start: int,
           text_end: int) -> TextValue:
    return TextValue(attribute=value.attribute, value=value.value, key=value.key,
                     confidence=value.confidence, source=value.source, sources=value.sources,
                     evidence=evidence, start=start, end=end, text_start=text_start,
                     text_end=text_end, in_review=value.in_review, review_id=value.review_id)


def _hints(page: PageText, near: Sequence[tuple[CatalogEntry, float]], open_slots: Sequence[str],
           threshold: float) -> list[TextValue]:
    hints = []
    for name in open_slots:
        votes: Mapping[str, float] = _votes(near, name)
        total = sum(votes.values())
        for value, weight in sorted(votes.items(), key=lambda kv: -kv[1]):
            confidence = round(weight / total, 4) if total else 0.0
            span = find_quote(page.text, value)
            if confidence < threshold or span is None:
                continue
            start, end = page.source_span(*span)
            hints.append(TextValue(
                attribute=name, value=value, key="", confidence=confidence,
                source=NEIGHBOR_SOURCE, sources=(NEIGHBOR_SOURCE,),
                evidence=page.text[span[0]:span[1]], start=start, end=end, text_start=span[0],
                text_end=span[1], in_review=False, review_id=None))
            break
    return hints


def _votes(near: Sequence[tuple[CatalogEntry, float]], name: str) -> dict[str, float]:
    votes: dict[str, float] = defaultdict(float)
    for entry, similarity in near:
        value = entry.values.get(name)
        if value:
            votes[value] += max(similarity, 0.0)
    return votes
