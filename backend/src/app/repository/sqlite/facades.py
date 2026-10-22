from app.domain.review import Alias, ReviewItem
from app.usecase.persistence import UnitOfWorkFactory
from app.usecase.review_query import ReviewPage, ReviewQuery


class ReviewRepository:
    def __init__(
        self, factory: UnitOfWorkFactory, read_factory: UnitOfWorkFactory | None = None
    ) -> None:
        self._factory = factory
        self._read_factory = read_factory or factory

    async def upsert_pending(self, item: ReviewItem) -> ReviewItem:
        async with self._factory() as unit:
            result = await unit.reviews.upsert_pending(item)
            await unit.commit()
            return result

    async def get(self, item_id: str) -> ReviewItem | None:
        async with self._read_factory() as unit:
            return await unit.reviews.get(item_id)

    async def page(self, query: ReviewQuery) -> ReviewPage:
        async with self._read_factory() as unit:
            return await unit.reviews.page(query)

    async def save(self, item: ReviewItem) -> None:
        async with self._factory() as unit:
            await unit.reviews.save(item)
            await unit.commit()


class AliasRepository:
    def __init__(
        self, factory: UnitOfWorkFactory, read_factory: UnitOfWorkFactory | None = None
    ) -> None:
        self._factory = factory
        self._read_factory = read_factory or factory

    async def all(self) -> list[Alias]:
        async with self._read_factory() as unit:
            return await unit.aliases.all()

    async def add(self, alias: Alias) -> None:
        async with self._factory() as unit:
            await unit.aliases.add(alias)
            await unit.commit()
