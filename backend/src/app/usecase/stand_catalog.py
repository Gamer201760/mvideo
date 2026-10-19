from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.lexicon import Lexicon
from app.domain.review import StandUnavailable
from app.usecase.catalog_schemas import CatalogSchemas
from app.usecase.extraction import RequiredAttributes
from app.usecase.stand_ports import StandExample, StandPack


@dataclass(frozen=True, slots=True, kw_only=True)
class CategoryInfo:
    category_id: int
    name: str
    path: str
    attributes: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class StandInfo:
    built_at: str
    threshold: float
    categories: tuple[CategoryInfo, ...]


class StandCatalog:
    def __init__(self, pack: StandPack | None, schemas: CatalogSchemas | None = None) -> None:
        self._pack = pack
        self._schemas = schemas
        self._info: StandInfo | None = None

    def info(self) -> StandInfo:
        pack = self._require()
        if self._schemas is not None:
            return StandInfo(
                built_at=pack.built_at,
                threshold=pack.threshold,
                categories=tuple(
                    CategoryInfo(
                        category_id=c.category_id,
                        name=c.path.split("/")[-1].strip(),
                        path=c.path,
                        attributes=tuple(sorted(f.attribute for f in c.fields)),
                    )
                    for c in sorted(self._schemas.snapshot(), key=lambda c: c.path)
                ),
            )
        if self._info is None:
            lexicon = Lexicon(pack.profiles, (), pack.priors)
            required = RequiredAttributes(pack.required, lexicon)
            categories = tuple(
                CategoryInfo(
                    category_id=c.category_id,
                    name=c.name,
                    path=c.path,
                    attributes=tuple(sorted(required.profiles(c.category_id))),
                )
                for c in sorted(pack.categories, key=lambda c: c.path)
            )
            self._info = StandInfo(
                built_at=pack.built_at, threshold=pack.threshold, categories=categories
            )
        return self._info

    def examples(self) -> Sequence[StandExample]:
        return self._require().examples

    def _require(self) -> StandPack:
        if self._pack is None:
            raise StandUnavailable()
        return self._pack
