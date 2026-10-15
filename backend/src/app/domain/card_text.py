import html
import re
from collections.abc import Sequence
from dataclasses import dataclass

BLOCK_TAG = re.compile(r"<\s*/?\s*(br|p|li|ul|ol|div|tr|h[1-6])\b[^>]*>", re.IGNORECASE)
ANY_TAG = re.compile(r"<[^>]{0,200}>")
SPACES = re.compile(r"[ \t   ]+")
NEWLINES = re.compile(r" *\n[\s]*")
TOKEN = re.compile(r"\d+(?:[.,]\d+)?|[a-zа-я]+")


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class SellerParam:
    name: str
    value: str
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class CardText:
    text: str
    match: str
    tokens: tuple[Token, ...]
    title_end: int
    seller_start: int

    def span(self, start: int, end: int) -> str:
        return self.text[start:end]

    def zone(self, start: int) -> str:
        if start < self.title_end:
            return "title"
        if start >= self.seller_start:
            return "seller"
        return "description"


def clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = BLOCK_TAG.sub("\n", raw)
    text = ANY_TAG.sub(" ", text)
    text = html.unescape(text)
    text = SPACES.sub(" ", text)
    text = NEWLINES.sub("\n", text)
    return text.strip()


def match_form(text: str) -> str:
    lowered = text.lower()
    if len(lowered) != len(text):
        lowered = "".join(ch.lower() if len(ch.lower()) == 1 else ch for ch in text)
    return lowered.replace("ё", "е")


def tokenize(match: str) -> tuple[Token, ...]:
    return tuple(Token(m.group(), m.start(), m.end()) for m in TOKEN.finditer(match))


def seller_line(param: SellerParam) -> str:
    unit = f" {param.unit}" if param.unit and param.unit not in param.value else ""
    return f"{param.name}: {param.value}{unit}"


def build_card_text(
    title: str | None, description: str | None, seller: Sequence[SellerParam]
) -> CardText:
    head = clean_text(title)
    body = clean_text(description)
    prefix = f"{head}\n{body}\n" if body else f"{head}\n"
    lines = "\n".join(seller_line(p) for p in seller)
    text = prefix + lines
    match = match_form(text)
    return CardText(
        text=text,
        match=match,
        tokens=tokenize(match),
        title_end=len(head),
        seller_start=len(prefix),
    )
