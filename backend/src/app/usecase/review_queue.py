from app.domain.review import (
    ReviewAction,
    ReviewItem,
    ReviewItemNotFound,
    ReviewStatus,
    resolve,
)
from app.usecase.stand_ports import AliasRepository, Clock, ReviewRepository


class ReviewQueue:
    def __init__(self, reviews: ReviewRepository, aliases: AliasRepository, clock: Clock) -> None:
        self._reviews = reviews
        self._aliases = aliases
        self._clock = clock

    async def list(self, status: ReviewStatus | None) -> list[ReviewItem]:
        items = await self._reviews.list(status)
        return sorted(items, key=lambda i: (i.status is not ReviewStatus.PENDING, i.created_at),
                      reverse=False)

    async def resolve(self, item_id: str, action: ReviewAction, value: str | None) -> ReviewItem:
        item = await self._reviews.get(item_id)
        if item is None:
            raise ReviewItemNotFound()
        resolved, alias = resolve(item, action, value, self._clock.now())
        await self._reviews.save(resolved)
        await self._aliases.add(alias)
        return resolved
