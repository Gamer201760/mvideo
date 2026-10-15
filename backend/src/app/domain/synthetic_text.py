import html
import random
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.domain.card_text import SellerParam, clean_text, seller_line

NOISE_DESCRIPTION_CHARS = 300
MENU = ("Каталог", "Акции", "Доставка", "Корзина", "Войти")


class InputKind(StrEnum):
    DESCRIPTION = "description"
    PAGE = "page"
    PARAGRAPH = "paragraph"


@dataclass(frozen=True, slots=True)
class SourceCard:
    title: str
    description: str
    params: Sequence[SellerParam]


def render(kind: InputKind, card: SourceCard, others: Sequence[SourceCard],
           rng: random.Random) -> str:
    match kind:
        case InputKind.DESCRIPTION:
            return clean_text(card.description)
        case InputKind.PAGE:
            return _page(card, others)
        case InputKind.PARAGRAPH:
            parts = [clean_text(card.title), clean_text(card.description).replace("\n", " "),
                     *(seller_line(p) for p in card.params)]
            rng.shuffle(parts)
            return " ".join(p for p in parts if p)


def _page(card: SourceCard, others: Sequence[SourceCard]) -> str:
    menu = "".join(f"<li><a href='/c/{i}'>{m}</a></li>" for i, m in enumerate(MENU))
    rows = "".join(f"<li><span>{html.escape(p.name)}</span>: "
                   f"<span>{html.escape(_value(p))}</span></li>" for p in card.params)
    similar = "".join(
        f"<div class='card'><a>{html.escape(clean_text(o.title))}</a>"
        f"<p>{html.escape(clean_text(o.description)[:NOISE_DESCRIPTION_CHARS])}</p></div>"
        for o in others)
    return (
        "<!doctype html><html><head><title>Интернет-магазин</title>"
        "<style>body{font:14px sans-serif}</style></head><body>"
        f"<header><nav><ul>{menu}</ul></nav></header>"
        "<script>window.dataLayer = window.dataLayer || [];</script>"
        f"<main><h1>{html.escape(clean_text(card.title))}</h1>"
        "<div class='price'>Цена по запросу</div>"
        f"<div class='description'>{card.description}</div>"
        f"<h2>Характеристики</h2><ul>{rows}</ul></main>"
        f"<aside><h2>Похожие товары</h2>{similar}</aside>"
        "<footer><p>© 2026 Магазин. Все права защищены.</p></footer></body></html>"
    )


def _value(param: SellerParam) -> str:
    return seller_line(param).split(": ", 1)[1]
