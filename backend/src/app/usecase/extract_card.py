import asyncio
from collections.abc import Sequence

from app.domain.acceptance import AcceptancePolicy
from app.domain.lexicon import Lexicon
from app.domain.review import Alias, StandUnavailable, UnknownCategory, alias_entry
from app.domain.review_decisions import latest_decisions
from app.usecase.baseline_ports import CardRecord
from app.usecase.card_identity import card_key
from app.usecase.card_result import CardResult
from app.usecase.catalog_pack import catalog_pack
from app.usecase.catalog_schemas import CatalogSchemas
from app.usecase.extraction import CardExtraction, RequiredAttributes, extract_card
from app.usecase.persistence import UnitOfWorkFactory
from app.usecase.review_query import ReviewQuery
from app.usecase.rule_assessment import assess_rules
from app.usecase.rule_recording import RuleRecording
from app.usecase.stand_ports import (
    AliasRepository,
    CandidateChooser,
    CardInput,
    Clock,
    IdGenerator,
    ReviewRepository,
    StandPack,
)

__all__ = ["BaselineChooser", "ExtractCard", "card_key"]


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
        acceptance: AcceptancePolicy | None = None,
    ) -> None:
        self._pack = pack
        self._aliases = aliases
        self._reviews = reviews
        self._chooser = chooser
        self._acceptance = acceptance or AcceptancePolicy()
        self._recording = RuleRecording(reviews, clock, ids, store, self._acceptance)
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
        rejected = {a for a, d in decisions.items() if d.resolved_value is None}
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
        assessment = await asyncio.to_thread(assess_rules, card, extraction, self._schemas)
        values = await self._recording.record(card, extraction, assessment, aliases)
        found = {v.attribute for v in values}
        missing = tuple(n for n in sorted(extraction.profiles) if n not in found)
        return CardResult(
            text=extraction.text.text,
            threshold=self._acceptance.threshold,
            values=tuple(values),
            missing=missing,
            rejections=tuple(r for r in assessment.rejections if r.attribute not in found),
            auto_accept_enabled=self._acceptance.enabled,
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
