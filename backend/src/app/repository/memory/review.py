import asyncio

from app.domain.review import Alias, ReviewItem, ReviewStatus


class MemoryReviewRepository:
    def __init__(self) -> None:
        self._items: dict[str, ReviewItem] = {}
        self._lock = asyncio.Lock()

    async def upsert_pending(self, item: ReviewItem) -> ReviewItem:
        async with self._lock:
            for existing in self._items.values():
                if (existing.status is ReviewStatus.PENDING and existing.card_key == item.card_key
                        and existing.attribute == item.attribute
                        and existing.evidence == item.evidence):
                    return existing
            self._items[item.id] = item
            return item

    async def get(self, item_id: str) -> ReviewItem | None:
        return self._items.get(item_id)

    async def save(self, item: ReviewItem) -> None:
        async with self._lock:
            self._items[item.id] = item

    async def list(self, status: ReviewStatus | None) -> list[ReviewItem]:
        return [i for i in self._items.values() if status is None or i.status is status]


class MemoryAliasRepository:
    def __init__(self) -> None:
        self._aliases: list[Alias] = []
        self._lock = asyncio.Lock()

    async def add(self, alias: Alias) -> None:
        async with self._lock:
            self._aliases = [a for a in self._aliases
                             if (a.attribute, a.evidence) != (alias.attribute, alias.evidence)]
            self._aliases.append(alias)

    async def all(self) -> list[Alias]:
        return list(self._aliases)
