from app.domain.review import (
    InvalidCorrection,
    ReviewAction,
    ReviewItem,
    ReviewItemNotFound,
    resolve,
)
from app.usecase.extract_card import card_key
from app.usecase.persistence import ReviewDecisions
from app.usecase.review_card import ReviewCard
from app.usecase.review_query import CardReviewState, ReviewPage, ReviewQuery
from app.usecase.stand_ports import AliasRepository, CardInput, Clock, ReviewRepository


class ReviewQueue:
    def __init__(
        self,
        reviews: ReviewRepository,
        aliases: AliasRepository,
        clock: Clock,
        decisions: ReviewDecisions | None = None,
    ) -> None:
        self._decisions = decisions
        self._reviews = reviews
        self._aliases = aliases
        self._clock = clock

    async def page(self, query: ReviewQuery) -> ReviewPage:
        return await self._reviews.page(query)

    async def for_card(self, card: CardInput) -> CardReviewState:
        key = card_key(card)
        page = await self._reviews.page(ReviewQuery(card_key=key, limit=None))
        return CardReviewState(key, page.items)

    async def card(self, item_id: str) -> ReviewCard:
        if self._decisions is None:
            raise ReviewItemNotFound()
        return await self._decisions.card(item_id)

    async def resolve(
        self,
        item_id: str,
        action: ReviewAction,
        value: str | None,
        *,
        override: bool = False,
        expected_value: str | None = None,
    ) -> ReviewItem:
        if self._decisions is not None:
            return await self._decisions.resolve(
                item_id,
                action.value,
                value,
                self._clock.now(),
                override=override,
                expected_value=expected_value,
            )
        item = await self._reviews.get(item_id)
        if item is None:
            raise ReviewItemNotFound()
        resolved, alias = resolve(
            item,
            action,
            value,
            self._clock.now(),
            override=override,
            expected_value=expected_value,
        )
        await self._reviews.save(resolved)
        if alias is not None:
            await self._aliases.add(alias)
        return resolved

    async def add(self, card: CardInput, attribute: str, value: str, evidence: str) -> ReviewItem:
        if self._decisions is None:
            raise InvalidCorrection()
        return await self._decisions.add(card, attribute, value, evidence, self._clock.now())
