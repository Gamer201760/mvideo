import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

GOLD_SUFFIX = "_search"
BRAND = "Бренд"
MODEL = "Модель"
SELLER_PARAM = "Продавец"
SERVICE_PARAMS = frozenset({"Потратить бонусы", "Акции", "Подборки"})
SERVICE_ATTRIBUTES = frozenset(
    {"Гарантия", "Гарантия предоставляется", "Срок службы", "Страна", MODEL, BRAND}
)
SERVICE_PREFIXES = ("ЗД ",)
SPEC_HEADER_PATTERN = r"(?i)характеристик[а-яё]*\s*:"
SPEC_LINE_PATTERN = r"(?m)^\s*[•·\-–—*]\s*[^:\n]{2,80}:\s*\S"
SPEC_MIN_LINES = 3

_SPEC_HEADER = re.compile(SPEC_HEADER_PATTERN)
_SPEC_LINE = re.compile(SPEC_LINE_PATTERN)


@dataclass(frozen=True, slots=True)
class Param:
    name: str
    value: str | None
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class Category:
    category_id: int
    parent_id: int | None
    name: str


@dataclass(frozen=True, slots=True)
class Offer:
    sku_id: int
    available: bool
    vendor: str | None
    model: str | None
    name: str | None
    category_id: int | None
    params: tuple[Param, ...]


@dataclass(frozen=True, slots=True)
class GoldValue:
    sku_id: int
    attribute: str
    value: str
    unit: str | None


@dataclass(frozen=True, slots=True)
class OfferCard:
    sku_id: int
    name: str | None
    category_id: int | None
    seller: str | None
    available: bool
    seller_params: tuple[Param, ...]


@dataclass(frozen=True, slots=True)
class SplitOffer:
    card: OfferCard
    gold: tuple[GoldValue, ...]


def is_gold_param(name: str) -> bool:
    return name.endswith(GOLD_SUFFIX)


def is_service_attribute(attribute: str) -> bool:
    return attribute in SERVICE_ATTRIBUTES or attribute.startswith(SERVICE_PREFIXES)


def gold_attribute(name: str) -> str:
    return name.removesuffix(GOLD_SUFFIX).strip()


def split_offer(offer: Offer) -> SplitOffer:
    seller: str | None = None
    seller_params: list[Param] = []
    gold: dict[str, GoldValue] = {}
    for param in offer.params:
        if is_gold_param(param.name):
            attribute = gold_attribute(param.name)
            if param.value is None or attribute in gold:
                continue
            gold[attribute] = GoldValue(offer.sku_id, attribute, param.value, param.unit)
        elif param.name == SELLER_PARAM:
            seller = param.value
        elif param.name not in SERVICE_PARAMS:
            seller_params.append(param)
    for attribute, value in ((BRAND, offer.vendor), (MODEL, offer.model)):
        if value:
            gold[attribute] = GoldValue(offer.sku_id, attribute, value, None)
    card = OfferCard(
        sku_id=offer.sku_id,
        name=offer.name,
        category_id=offer.category_id,
        seller=seller,
        available=offer.available,
        seller_params=tuple(seller_params),
    )
    return SplitOffer(card=card, gold=tuple(gold.values()))


def has_spec_block(text: str | None) -> bool:
    if not text:
        return False
    if _SPEC_HEADER.search(text):
        return True
    return len(_SPEC_LINE.findall(text)) >= SPEC_MIN_LINES


def category_paths(categories: Iterable[Category]) -> dict[int, str]:
    by_id: Mapping[int, Category] = {c.category_id: c for c in categories}
    paths: dict[int, str] = {}
    for category_id in by_id:
        names: list[str] = []
        seen: set[int] = set()
        current: int | None = category_id
        while current is not None and current in by_id and current not in seen:
            seen.add(current)
            names.append(by_id[current].name)
            current = by_id[current].parent_id
        paths[category_id] = " / ".join(reversed(names))
    return paths
