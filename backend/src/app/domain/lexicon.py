from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass

from app.domain.card_text import Token, match_form, tokenize
from app.domain.profile import AttributeProfile
from app.domain.values import color_word

MIN_ENTRY_CHARS = 2


@dataclass(frozen=True, slots=True)
class LexiconEntry:
    attribute: str
    tokens: tuple[str, ...]
    key: str
    display: str


@dataclass(frozen=True, slots=True)
class EntryMatch:
    entry: LexiconEntry
    first: int
    last: int


def match_token(token: str) -> str:
    if token[0].isdigit():
        return token.replace(",", ".")
    return color_word(token)


def value_tokens(value: str) -> tuple[str, ...]:
    return tuple(match_token(t.text) for t in tokenize(match_form(value)))


class Lexicon:
    def __init__(
        self,
        profiles: Mapping[str, AttributeProfile],
        entries: Iterable[LexiconEntry],
        priors: Mapping[tuple[int, str], Mapping[str, float]],
    ) -> None:
        self.profiles = dict(profiles)
        self._priors = {k: dict(v) for k, v in priors.items()}
        self._index: dict[str, list[LexiconEntry]] = defaultdict(list)
        self._display: dict[tuple[str, str], str] = {}
        for entry in entries:
            if not entry.tokens or sum(len(t) for t in entry.tokens) < MIN_ENTRY_CHARS:
                continue
            self._index[entry.tokens[0]].append(entry)
            self._display.setdefault((entry.attribute, entry.key), entry.display)

    @property
    def size(self) -> int:
        return sum(len(v) for v in self._index.values())

    def prior(self, category: int | None, attribute: str, key: str) -> float:
        if category is None:
            return 0.0
        return self._priors.get((category, attribute), {}).get(key, 0.0)

    def category_values(self, category: int | None, attribute: str) -> Mapping[str, float]:
        if category is None:
            return {}
        return self._priors.get((category, attribute), {})

    def display(self, attribute: str, key: str) -> str | None:
        return self._display.get((attribute, key))

    def matches(
        self, tokens: Sequence[Token], attributes: frozenset[str]
    ) -> Iterator[EntryMatch]:
        normalized = [match_token(t.text) for t in tokens]
        for i, first in enumerate(normalized):
            for entry in self._index.get(first, ()):
                if entry.attribute not in attributes:
                    continue
                end = i + len(entry.tokens)
                if end <= len(normalized) and tuple(normalized[i:end]) == entry.tokens:
                    yield EntryMatch(entry, i, end - 1)
