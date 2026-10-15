import mmap
from collections.abc import Iterator
from pathlib import Path

from app.adapter.catalog.pickle_stream import Node, stream_list_items
from app.domain.catalog import Category, Offer, Param

_KEYS = frozenset({"category", "offer"})


def _int(value: Node) -> int | None:
    if isinstance(value, str):
        value = value.strip()
        return int(value) if value.isdigit() else None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _text(value: Node) -> str | None:
    if isinstance(value, str):
        stripped = " ".join(value.split())
        return stripped or None
    if isinstance(value, dict):
        return _text(value.get("#text"))
    return None


def _params(raw: Node) -> tuple[Param, ...]:
    items = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
    params: list[Param] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("@name"))
        if name is None:
            continue
        params.append(Param(name, _text(item.get("#text")), _text(item.get("@unit"))))
    return tuple(params)


def _category_id(node: dict[str, Node]) -> int | None:
    direct = _int(node.get("categoryId"))
    if direct is not None:
        return direct
    nested = node.get("categories")
    if isinstance(nested, dict):
        value = nested.get("categoryId")
        if isinstance(value, list):
            value = value[0] if value else None
        return _int(value)
    return None


def to_category(node: Node) -> Category | None:
    if not isinstance(node, dict):
        return None
    category_id = _int(node.get("@id"))
    if category_id is None:
        return None
    return Category(category_id, _int(node.get("@parentId")), _text(node.get("#text")) or "")


def to_offer(node: Node) -> Offer | None:
    if not isinstance(node, dict):
        return None
    sku_id = _int(node.get("@id"))
    if sku_id is None:
        return None
    return Offer(
        sku_id=sku_id,
        available=node.get("@available") == "true",
        vendor=_text(node.get("vendor")),
        model=_text(node.get("model")),
        name=_text(node.get("name")),
        category_id=_category_id(node),
        params=_params(node.get("param")),
    )


class PickledYmlCatalog:
    def __init__(self, path: Path) -> None:
        self._path = path

    def items(self) -> Iterator[Category | Offer]:
        with (
            self._path.open("rb") as file,
            mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as mm,
        ):
            for key, node in stream_list_items(mm, _KEYS):
                item = to_category(node) if key == "category" else to_offer(node)
                if item is not None:
                    yield item
