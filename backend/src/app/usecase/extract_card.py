import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.candidate import Candidate
from app.domain.lexicon import Lexicon
from app.domain.review import (
    REVIEW_CONFIDENCE,
    REVIEW_SOURCE,
    Alias,
    ReviewItem,
    ReviewStatus,
    StandUnavailable,
    UnknownCategory,
    alias_entry,
    evidence_form,
)
from app.domain.scoring import Pick
from app.usecase.baseline_ports import CardRecord
from app.usecase.extraction import CardExtraction, RequiredAttributes, extract_card
from app.usecase.stand_ports import (
    AliasRepository,
    CandidateChooser,
    CardInput,
    Clock,
    IdGenerator,
    ReviewRepository,
    StandPack,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtractedValue:
    attribute: str
    value: str
    confidence: float
    source: str
    sources: tuple[str, ...]
    evidence: str
    start: int
    end: int
    in_review: bool
    review_id: str | None
    key: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class CardResult:
    text: str
    threshold: float
    values: tuple[ExtractedValue, ...]
    missing: tuple[str, ...]


class BaselineChooser:
    async def choose(self, extraction: CardExtraction, threshold: float, category_id: int | None,
                     known: frozenset[str]) -> CardExtraction:
        return extraction


class ExtractCard:
    def __init__(self, pack: StandPack | None, aliases: AliasRepository,
                 reviews: ReviewRepository, chooser: CandidateChooser, clock: Clock,
                 ids: IdGenerator) -> None:
        self._pack = pack
        self._aliases = aliases
        self._reviews = reviews
        self._chooser = chooser
        self._clock = clock
        self._ids = ids
        self._cache: tuple[tuple[Alias, ...], Lexicon, RequiredAttributes] | None = None

    async def execute(self, card: CardInput) -> CardResult:
        pack = self._require_pack()
        if card.category_id is not None and card.category_id not in {
            c.category_id for c in pack.categories
        }:
            raise UnknownCategory()
        aliases = await self._aliases.all()
        lexicon, required = self._dictionaries(pack, aliases)
        record = CardRecord(0, card.category_id, None, card.title, card.description,
                            card.seller_params, None)
        extraction = extract_card(record, required, lexicon, pack.threshold)
        known = frozenset(a for a in extraction.profiles
                          if lexicon.category_values(card.category_id, a))
        extraction = await self._chooser.choose(extraction, pack.threshold, card.category_id,
                                                known)
        confirmed = {(a.attribute, evidence_form(a.evidence)): a for a in aliases}
        values = []
        for name in sorted(extraction.profiles):
            value = await self._value(card, name, extraction, confirmed)
            if value is not None:
                values.append(value)
        found = {v.attribute for v in values}
        missing = tuple(n for n in sorted(extraction.profiles) if n not in found)
        return CardResult(text=extraction.text.text, threshold=pack.threshold,
                          values=tuple(values), missing=missing)

    def _require_pack(self) -> StandPack:
        if self._pack is None:
            raise StandUnavailable()
        return self._pack

    def _dictionaries(self, pack: StandPack,
                      aliases: Sequence[Alias]) -> tuple[Lexicon, RequiredAttributes]:
        version = tuple(aliases)
        if self._cache is not None and self._cache[0] == version:
            return self._cache[1], self._cache[2]
        extra = [alias_entry(a, pack.profiles[a.attribute].numeric)
                 for a in aliases if a.attribute in pack.profiles]
        lexicon = Lexicon(pack.profiles, [*pack.entries, *extra], pack.priors)
        required = RequiredAttributes(pack.required, lexicon)
        self._cache = (version, lexicon, required)
        return lexicon, required

    async def _value(self, card: CardInput, name: str, extraction: CardExtraction,
                     confirmed: Mapping[tuple[str, str], Alias]) -> ExtractedValue | None:
        for candidate in extraction.candidates:
            alias = confirmed.get((name, evidence_form(candidate.evidence)))
            if candidate.attribute == name and alias is not None:
                return _reviewed(candidate, alias)
        pick = extraction.picks.get(name)
        if pick is not None:
            return _from_pick(name, pick, None)
        pending = extraction.review.get(name)
        if pending is None:
            return None
        item = await self._reviews.upsert_pending(self._item(card, name, pending))
        return _from_pick(name, pending, item.id)

    def _item(self, card: CardInput, name: str, pick: Pick) -> ReviewItem:
        return ReviewItem(
            id=self._ids.new(), card_key=card_key(card), category_id=card.category_id,
            title=card.title, attribute=name, value=pick.candidate.value,
            confidence=pick.confidence, source=pick.candidate.source,
            evidence=pick.candidate.evidence, status=ReviewStatus.PENDING, resolved_value=None,
            created_at=self._clock.now(), resolved_at=None,
        )


def card_key(card: CardInput) -> str:
    raw = "\n".join([card.title, card.description, str(card.category_id)])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _reviewed(candidate: Candidate, alias: Alias) -> ExtractedValue:
    return ExtractedValue(
        attribute=candidate.attribute, value=alias.value, confidence=REVIEW_CONFIDENCE,
        source=REVIEW_SOURCE, sources=(REVIEW_SOURCE, candidate.source),
        evidence=candidate.evidence, start=candidate.start, end=candidate.end,
        in_review=False, review_id=None,
    )


def _from_pick(name: str, pick: Pick, review_id: str | None) -> ExtractedValue:
    c = pick.candidate
    return ExtractedValue(
        attribute=name, value=c.value, confidence=pick.confidence, source=c.source,
        sources=pick.sources, evidence=c.evidence, start=c.start, end=c.end,
        in_review=review_id is not None, review_id=review_id, key=c.key,
    )
