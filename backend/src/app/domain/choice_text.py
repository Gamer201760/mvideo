from collections.abc import Iterable

from app.domain.card_text import CardText
from app.domain.lexicon import match_token, value_tokens
from app.domain.profile import STEM

MAX_EVIDENCE_CHARS = 120
MIN_STEM_WORD = 3
MAX_STATE_CHARS = 2500
STATE_WINDOW = 100
SELLER_CHARS = 800
LEAD_CHARS = 600
GAP = " … "


def locate(card: CardText, value: str) -> tuple[int, int] | None:
    wanted = value_tokens(value)
    if not wanted:
        return None
    tokens = card.tokens
    normalized = [match_token(t.text) for t in tokens]
    size = len(wanted)
    for i in range(len(normalized) - size + 1):
        if tuple(normalized[i:i + size]) == wanted:
            return tokens[i].start, tokens[i + size - 1].end
    return None



def _stem(word: str) -> str:
    return word if word[0].isdigit() else word[:STEM]



def locate_stems(card: CardText, value: str) -> tuple[int, int] | None:
    wanted = {_stem(w) for w in value_tokens(value) if len(w) >= MIN_STEM_WORD or w[0].isdigit()}
    if not wanted:
        return None
    first: dict[str, int] = {}
    for index, token in enumerate(card.tokens):
        stem = _stem(match_token(token.text))
        if stem in wanted and stem not in first:
            first[stem] = index
    if len(first) < len(wanted):
        return None
    indices = sorted(first.values())
    start, end = card.tokens[indices[0]].start, card.tokens[indices[-1]].end
    if end - start > MAX_EVIDENCE_CHARS:
        token = card.tokens[indices[0]]
        return token.start, token.end
    return start, end



def _merge_windows(spans: Iterable[tuple[int, int]], low: int, high: int) -> list[tuple[int, int]]:
    windows = sorted((max(low, s - STATE_WINDOW), min(high, e + STATE_WINDOW))
                     for s, e in spans if low <= s < high)
    merged: list[tuple[int, int]] = []
    for start, end in windows:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged



def compact_state(
    card: CardText, category: str | None, spans: Iterable[tuple[int, int]]
) -> dict[str, str]:
    title = card.text[:card.title_end]
    body_start, body_end = card.title_end, card.seller_start
    windows = _merge_windows(spans, body_start, body_end)
    if windows:
        body = GAP.join(card.text[s:e].strip() for s, e in windows)
    else:
        body = card.text[body_start:min(body_end, body_start + LEAD_CHARS)].strip()
    seller = card.text[card.seller_start:card.seller_start + SELLER_CHARS]
    text = "\n".join(part for part in (title, body, seller) if part)
    state = {"card": text[:MAX_STATE_CHARS]}
    if category:
        state["category"] = category
    return state
