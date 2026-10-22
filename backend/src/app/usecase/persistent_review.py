from datetime import datetime

from app.domain.review import ReviewAction, ReviewItem, ReviewItemNotFound, resolve
from app.usecase.persistence import UnitOfWorkFactory
from app.usecase.review_addition import add_review
from app.usecase.review_card import ReviewCard
from app.usecase.stand_ports import CardInput


class PersistentReview:
    def __init__(
        self, factory: UnitOfWorkFactory, read_factory: UnitOfWorkFactory | None = None
    ) -> None:
        self._factory = factory
        self._read_factory = read_factory or factory

    async def card(self, item_id: str) -> ReviewCard:
        async with self._read_factory() as unit:
            item = await unit.reviews.get(item_id)
            card = await unit.cards.get(item.card_key) if item else None
        if card is None:
            raise ReviewItemNotFound()
        return card

    async def resolve(
        self,
        item_id: str,
        action: str,
        value: str | None,
        now: datetime,
        *,
        override: bool = False,
        expected_value: str | None = None,
    ) -> ReviewItem:
        async with self._factory() as unit:
            item = await unit.reviews.get(item_id)
            if item is None:
                raise ReviewItemNotFound()
            if item.resolved_at is not None:
                expected = (
                    (value or "").strip()
                    if action == "correct"
                    else None
                    if action == "reject"
                    else item.value
                )
                if item.resolved_value == expected and (
                    (action == "correct" and item.status.value == "corrected")
                    or (action == "accept" and item.status.value == "accepted")
                    or (action == "reject" and item.status.value == "rejected")
                ):
                    return item
            resolved, alias = resolve(
                item,
                ReviewAction(action),
                value,
                now,
                override=override,
                expected_value=expected_value,
            )
            await unit.reviews.save(resolved)
            if alias is not None:
                await unit.aliases.add(alias)
            await unit.commit()
            return resolved

    async def add(
        self, card: CardInput, attribute: str, value: str, evidence: str, now: datetime
    ) -> ReviewItem:
        async with self._factory() as unit:
            result = await add_review(unit, card, attribute, value, evidence, now)
            await unit.commit()
            return result
