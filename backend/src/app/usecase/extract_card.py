import asyncio
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace

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
from app.domain.review_decisions import latest_decisions
from app.domain.scoring import Pick
from app.usecase.baseline_ports import CardRecord
from app.usecase.card_result import CardResult, ExtractedValue
from app.usecase.catalog_pack import catalog_pack
from app.usecase.catalog_schemas import CatalogSchemas
from app.usecase.extraction import CardExtraction, RequiredAttributes, extract_card
from app.usecase.persistence import UnitOfWorkFactory
from app.usecase.review_card import ReviewCard
from app.usecase.review_query import ReviewQuery
from app.usecase.rule_reviews import apply_decisions
from app.usecase.stand_ports import (
    AliasRepository,
    CandidateChooser,
    CardInput,
    Clock,
    IdGenerator,
    ReviewRepository,
    StandPack,
)


class BaselineChooser:
    async def choose(
        self,
        extraction: CardExtraction,
        threshold: float,
        category_id: int | None,
        known: frozenset[str],
    ) -> CardExtraction:
        return extraction


class ExtractCard:
    def __init__(
        self,
        pack: StandPack | None,
        aliases: AliasRepository,
        reviews: ReviewRepository,
        chooser: CandidateChooser,
        clock: Clock,
        ids: IdGenerator,
        store: UnitOfWorkFactory | None = None,
        schemas: CatalogSchemas | None = None,
    ) -> None:
        self._pack = pack
        self._aliases = aliases
        self._reviews = reviews
        self._chooser = chooser
        self._clock = clock
        self._ids = ids
        self._store = store
        self._schemas = schemas
        self._cache: tuple[StandPack, tuple[Alias, ...], Lexicon, RequiredAttributes] | None = None

    async def execute(self, card: CardInput) -> CardResult:
        pack = await asyncio.to_thread(self._current_pack, card.category_id)
        if card.category_id is not None and card.category_id not in {
            c.category_id for c in pack.categories
        }:
            raise UnknownCategory()
        page = await self._reviews.page(ReviewQuery(card_key=card_key(card), limit=None))
        decisions = latest_decisions(page.items)
        rejected = {a for a, d in decisions.items() if d.status is ReviewStatus.REJECTED}
        aliases = [
            a
            for a in await self._aliases.all()
            if a.category_id == card.category_id
            and a.card_key == card_key(card)
            and a.attribute not in rejected
        ]
        lexicon, required = await asyncio.to_thread(self._dictionaries, pack, aliases)
        record = CardRecord(
            0, card.category_id, None, card.title, card.description, card.seller_params, None
        )
        extraction = await asyncio.to_thread(
            extract_card, record, required, lexicon, pack.threshold
        )
        known = frozenset(
            a for a in extraction.profiles if lexicon.category_values(card.category_id, a)
        )
        extraction = await self._chooser.choose(extraction, pack.threshold, card.category_id, known)
        if self._store is not None:
            async with self._store() as unit:
                await unit.cards.save(card_key(card), ReviewCard(card, "rules"))
                await unit.commit()
        confirmed = {(a.attribute, evidence_form(a.evidence)): a for a in aliases}
        values = []
        for name in sorted(extraction.profiles):
            if name in rejected:
                continue
            value = await self._value(card, name, extraction, confirmed)
            if value is not None:
                values.append(value)
        values = apply_decisions(values, decisions, extraction.text.text)
        found = {v.attribute for v in values}
        missing = tuple(n for n in sorted(extraction.profiles) if n not in found)
        return CardResult(
            text=extraction.text.text,
            threshold=pack.threshold,
            values=tuple(values),
            missing=missing,
        )

    def _require_pack(self) -> StandPack:
        if self._pack is None:
            raise StandUnavailable()
        return self._pack

    def _current_pack(self, category_id: int | None) -> StandPack:
        template = self._require_pack()
        if self._schemas is None:
            return template
        categories = tuple(
            c
            for c in self._schemas.snapshot()
            if category_id is None or c.category_id == category_id
        )
        if not categories:
            raise UnknownCategory()
        return catalog_pack(
            categories,
            built_at=template.built_at,
            threshold=template.threshold,
            examples=template.examples,
        )

    def _dictionaries(
        self, pack: StandPack, aliases: Sequence[Alias]
    ) -> tuple[Lexicon, RequiredAttributes]:
        version = tuple(aliases)
        cached = self._cache
        if cached is not None and cached[0] == pack and cached[1] == version:
            return cached[2], cached[3]
        extra = [
            alias_entry(a, pack.profiles[a.attribute].numeric, pack.profiles[a.attribute].unit)
            for a in aliases
            if a.attribute in pack.profiles
        ]
        lexicon = Lexicon(pack.profiles, [*pack.entries, *extra], pack.priors)
        required = RequiredAttributes(pack.required, lexicon)
        self._cache = (pack, version, lexicon, required)
        return lexicon, required

    async def _value(
        self,
        card: CardInput,
        name: str,
        extraction: CardExtraction,
        confirmed: Mapping[tuple[str, str], Alias],
    ) -> ExtractedValue | None:
        for candidate in extraction.candidates:
            alias = confirmed.get((name, evidence_form(candidate.evidence)))
            if candidate.attribute == name and alias is not None:
                return _reviewed(candidate, alias)
        pick = extraction.picks.get(name)
        if pick is not None:
            item = await self._reviews.upsert_pending(
                replace(self._item(card, name, pick), status=ReviewStatus.AUTO_ACCEPTED)
            )
            return _from_pick(name, pick, item.id, in_review=False)
        pending = extraction.review.get(name)
        if pending is None:
            return None
        item = await self._reviews.upsert_pending(self._item(card, name, pending))
        return _from_pick(name, pending, item.id)

    def _item(self, card: CardInput, name: str, pick: Pick) -> ReviewItem:
        return ReviewItem(
            id=self._ids.new(),
            card_key=card_key(card),
            category_id=card.category_id,
            title=card.title,
            attribute=name,
            value=pick.candidate.value,
            confidence=pick.confidence,
            source=pick.candidate.source,
            evidence=pick.candidate.evidence,
            status=ReviewStatus.PENDING,
            resolved_value=None,
            created_at=self._clock.now(),
            resolved_at=None,
        )


def card_key(card: CardInput) -> str:
    raw = json.dumps(
        [
            card.title,
            card.description,
            card.category_id,
            [(p.name, p.value, p.unit) for p in card.seller_params],
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _reviewed(candidate: Candidate, alias: Alias) -> ExtractedValue:
    return ExtractedValue(
        attribute=candidate.attribute,
        value=alias.value,
        confidence=REVIEW_CONFIDENCE,
        source=REVIEW_SOURCE,
        sources=(REVIEW_SOURCE, candidate.source),
        evidence=candidate.evidence,
        start=candidate.start,
        end=candidate.end,
        in_review=False,
        review_id=None,
    )


def _from_pick(
    name: str, pick: Pick, review_id: str | None, *, in_review: bool | None = None
) -> ExtractedValue:
    c = pick.candidate
    return ExtractedValue(
        attribute=name,
        value=c.value,
        confidence=pick.confidence,
        source=c.source,
        sources=pick.sources,
        evidence=c.evidence,
        start=c.start,
        end=c.end,
        in_review=review_id is not None if in_review is None else in_review,
        review_id=review_id,
    )
