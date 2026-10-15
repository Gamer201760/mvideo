import html
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass

HTML_HINT = re.compile(r"<\s*(?:[a-z][a-z0-9]*|/[a-z]|!--)", re.IGNORECASE)
DROPPED = ("script", "style", "noscript", "svg", "template", "head", "nav", "footer", "aside",
           "button", "select", "iframe")
BLOCKS = ("br", "p", "li", "ul", "ol", "div", "tr", "td", "th", "table", "dt", "dd", "dl",
          "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "main", "body", "title")
HTML_TOKEN = re.compile(
    r"(?P<comment><!--.*?-->)"
    rf"|(?P<drop><(?P<dropped>{'|'.join(DROPPED)})\b[^>]*>.*?</(?P=dropped)\s*>)"
    r"|(?P<tag></?\s*(?P<name>[a-z][a-z0-9]*)\b[^>]*>|<!?[a-z][^>]*>)"
    r"|(?P<entity>&(?:#\d{1,7}|#x[0-9a-f]{1,6}|[a-z][a-z0-9]{1,31});)",
    re.IGNORECASE | re.DOTALL,
)
CHROME_LINE = re.compile(
    r"^(?:войти|вход|выход|регистрация|корзина|каталог|избранное|сравнение|меню|поиск|"
    r"главная|личный кабинет|акции|доставка|оплата|контакты|в корзину|купить|"
    r"добавить в корзину|показать еще|подробнее|назад|наверх)$"
    r"|©|все права защищены|cookie",
    re.IGNORECASE,
)
NOISE_HEADING = re.compile(
    r"^(?:похожие товары|с этим товаром (?:часто )?покупают|вы (?:недавно )?смотрели|"
    r"рекомендуем|отзывы(?: покупателей)?|аксессуары(?: к товару)?|сопутствующие товары|"
    r"другие товары|смотрите также)\s*(?:\(\d+\))?\s*:?$",
    re.IGNORECASE,
)
NOISE_HEADING_CHARS = 60
MIN_TEXT_BEFORE_NOISE = 200
CHROME_WORDS = 6
SPACE = re.compile(r"\s")
QUOTE_SPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class PageText:
    source: str
    text: str
    starts: tuple[int, ...]
    ends: tuple[int, ...]

    def source_span(self, start: int, end: int) -> tuple[int, int]:
        if not 0 <= start < end <= len(self.text):
            raise ValueError(f"span {start}:{end} is outside the cleaned text")
        return self.starts[start], self.ends[end - 1]


@dataclass(frozen=True, slots=True)
class _Char:
    char: str
    start: int
    end: int


def clean_page(raw: str) -> PageText:
    is_html = HTML_HINT.search(raw) is not None
    chars = list(_html_chars(raw) if is_html else _plain_chars(raw))
    lines = _filter(_lines(chars, is_html))
    out: list[_Char] = []
    for line in lines:
        if out:
            out.append(_Char("\n", out[-1].end, out[-1].end))
        out.extend(line)
    return PageText(raw, "".join(c.char for c in out), tuple(c.start for c in out),
                    tuple(c.end for c in out))


def _plain_chars(raw: str) -> Iterator[_Char]:
    for index, char in enumerate(raw):
        yield _Char(char, index, index + 1)


def _html_chars(raw: str) -> Iterator[_Char]:
    position = 0
    for match in HTML_TOKEN.finditer(raw):
        yield from (_Char(raw[i], i, i + 1) for i in range(position, match.start()))
        position = match.end()
        if match.group("entity"):
            decoded = html.unescape(match.group())
            if decoded == match.group():
                yield from (_Char(raw[i], i, i + 1) for i in range(match.start(), match.end()))
            else:
                yield from (_Char(c, match.start(), match.end()) for c in decoded)
        elif match.group("drop") or _is_block(match.group("name")):
            yield _Char("\n", match.start(), match.start())
        elif match.group("tag"):
            yield _Char(" ", match.start(), match.start())
    yield from (_Char(raw[i], i, i + 1) for i in range(position, len(raw)))


def _is_block(name: str | None) -> bool:
    return name is not None and name.lower() in BLOCKS


def _lines(chars: list[_Char], is_html: bool) -> list[list[_Char]]:
    lines: list[list[_Char]] = [[]]
    gap: list[_Char] = []
    for char in chars:
        if SPACE.match(char.char):
            gap.append(char)
            continue
        if gap:
            breaks = any(g.char == "\n" and (not is_html or g.start == g.end) for g in gap)
            if breaks:
                lines.append([])
            elif lines[-1]:
                lines[-1].append(_Char(" ", gap[0].start, gap[0].start))
            gap = []
        lines[-1].append(char)
    return [line for line in lines if line]


def _filter(lines: list[list[_Char]]) -> list[list[_Char]]:
    texts = ["".join(c.char for c in line) for line in lines]
    keys = [t.casefold() for t in texts]
    repeated = {k for k, n in Counter(keys).items()
                if n > 1 and 2 <= len(k.split()) <= CHROME_WORDS}
    kept: list[list[_Char]] = []
    size = 0
    for line, text, key in zip(lines, texts, keys, strict=True):
        if key in repeated or CHROME_LINE.search(text):
            continue
        if (size >= MIN_TEXT_BEFORE_NOISE and len(text) <= NOISE_HEADING_CHARS
                and NOISE_HEADING.match(text)):
            break
        kept.append(line)
        size += len(text)
    return kept


def find_quote(text: str, fragment: str) -> tuple[int, int] | None:
    wanted = QUOTE_SPACE.sub(" ", _fold(fragment)).strip()
    if not wanted:
        return None
    folded: list[str] = []
    index: list[int] = []
    for position, char in enumerate(text):
        if SPACE.match(char):
            if folded and folded[-1] == " ":
                continue
            char = " "
        folded.append(_fold(char))
        index.append(position)
    haystack = "".join(folded)
    start = haystack.find(wanted)
    while start >= 0:
        end = start + len(wanted)
        if _bounded(haystack, start, end):
            return index[start], index[end - 1] + 1
        start = haystack.find(wanted, start + 1)
    return None


def _fold(text: str) -> str:
    folded = text.casefold().replace("ё", "е")
    return folded if len(folded) == len(text) else text


def _bounded(text: str, start: int, end: int) -> bool:
    before = start == 0 or not (text[start - 1].isalnum() and text[start].isalnum())
    after = end == len(text) or not (text[end].isalnum() and text[end - 1].isalnum())
    return before and after
