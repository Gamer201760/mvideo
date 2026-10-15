import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.candidate import Candidate
from app.domain.card_text import CardText
from app.domain.choice_text import locate, locate_stems
from app.domain.decision import (
    BinaryQuestion,
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionRequest,
    Question,
    ScoreQuestion,
)
from app.domain.profile import AttributeProfile
from app.domain.scoring import candidate_score

NOT_STATED = "не указано"
NOT_STATED_HINT = "значения этого атрибута в тексте карточки нет"
DICTIONARY_SOURCE = "decision_dictionary"
MAX_OPTION_CHARS = 80
MAX_EVIDENCE_CHARS = 120
INSTRUCTIONS = (
    "Значение атрибута «{attribute}»{unit} по тексту карточки. "
    "Если в тексте его нет — «" + NOT_STATED + "»."
)


@dataclass(frozen=True, slots=True)
class ChoiceOption:
    name: str
    hint: str
    candidate: Candidate | None


@dataclass(frozen=True, slots=True)
class ChoiceSlot:
    attribute: str
    question_key: str
    options: tuple[ChoiceOption, ...]
    from_dictionary: bool
    unit: str = ""

    def question(self) -> ChoiceQuestion:
        criteria = {o.name: o.hint for o in self.options}
        criteria[NOT_STATED] = NOT_STATED_HINT
        unit = f", {self.unit}" if self.unit else ""
        return ChoiceQuestion(INSTRUCTIONS.format(attribute=self.attribute, unit=unit), criteria)


@dataclass(frozen=True, slots=True)
class Chosen:
    attribute: str
    candidate: Candidate | None
    probability: float


def _unique_name(base: str, taken: set[str]) -> str:
    name = base[:MAX_OPTION_CHARS].strip() or "значение"
    if name == NOT_STATED:
        name = f"{name} (значение)"
    suffix = 2
    unique = name
    while unique in taken:
        unique = f"{name} #{suffix}"
        suffix += 1
    taken.add(unique)
    return unique


def candidate_slot(
    attribute: str, key: str, candidates: Iterable[Candidate], profile: AttributeProfile,
    top_k: int,
) -> ChoiceSlot | None:
    best: dict[str, tuple[float, Candidate]] = {}
    for c in candidates:
        score = candidate_score(c, profile)
        current = best.get(c.key)
        if current is None or score > current[0] or (
            score == current[0] and c.start < current[1].start
        ):
            best[c.key] = (score, c)
    ranked = sorted(best.values(), key=lambda item: (-item[0], item[1].start))[:top_k]
    if not ranked:
        return None
    taken: set[str] = set()
    options = tuple(
        ChoiceOption(_unique_name(c.value, taken), f"фрагмент: «{c.evidence[:MAX_EVIDENCE_CHARS]}»",
                     c)
        for _, c in ranked
    )
    return ChoiceSlot(attribute, key, options, from_dictionary=False, unit=profile.unit)


def mixed_slot(
    attribute: str, key: str, candidates: Iterable[Candidate], profile: AttributeProfile,
    top_k: int, values: Mapping[str, float], display: Mapping[str, str], extra_k: int,
) -> ChoiceSlot | None:
    base = candidate_slot(attribute, key, candidates, profile, top_k)
    if base is None:
        return dictionary_slot(attribute, key, values, display, extra_k, profile.unit)
    known = {o.candidate.key for o in base.options if o.candidate is not None}
    taken = {o.name for o in base.options}
    ranked = [k for k, _ in sorted(values.items(), key=lambda kv: (-kv[1], kv[0]))
              if k not in known][:extra_k]
    extra = tuple(
        ChoiceOption(_unique_name(display.get(k, k), taken), "значение из справочника каталога",
                     _placeholder(attribute, k, display.get(k, k)))
        for k in ranked
    )
    return ChoiceSlot(attribute, key, base.options + extra, from_dictionary=False,
                      unit=profile.unit)


def dictionary_slot(
    attribute: str, key: str, values: Mapping[str, float], display: Mapping[str, str],
    top_k: int, unit: str = "",
) -> ChoiceSlot | None:
    ranked = sorted(values.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
    if not ranked:
        return None
    taken: set[str] = set()
    options = tuple(
        ChoiceOption(_unique_name(display.get(k, k), taken), "значение из справочника каталога",
                     _placeholder(attribute, k, display.get(k, k)))
        for k, _ in ranked
    )
    return ChoiceSlot(attribute, key, options, from_dictionary=True, unit=unit)


def _placeholder(attribute: str, key: str, value: str) -> Candidate:
    return Candidate(attribute, key, value, "", -1, -1, DICTIONARY_SOURCE, "dictionary", 0.0, 0.0,
                     0)


def build_request(state: Mapping[str, str], slots: Sequence[ChoiceSlot]) -> DecisionRequest:
    return DecisionRequest(state=dict(state), questions={s.question_key: s.question() for s in slots})


def resolve(card: CardText, slot: ChoiceSlot, answer: ChoiceAnswer) -> Chosen | None:
    if answer.choice == NOT_STATED:
        return None
    option = next((o for o in slot.options if o.name == answer.choice), None)
    if option is None or option.candidate is None:
        return None
    candidate = option.candidate
    if candidate.start < 0:
        span = locate(card, candidate.value) or locate_stems(card, candidate.value)
        if span is None:
            return None
        start, end = span
        candidate = Candidate(candidate.attribute, candidate.key, candidate.value,
                              card.span(start, end), start, end, DICTIONARY_SOURCE,
                              card.zone(start), 0.0, 0.0, 0)
    probability = answer.probabilities.get(answer.choice, answer.confidence)
    return Chosen(slot.attribute, candidate, round(probability, 4))


def _question_json(question: Question) -> dict[str, Any]:
    match question:
        case ChoiceQuestion(instructions, options):
            return {"type": "choice", "instructions": instructions, "criteria": dict(options)}
        case ScoreQuestion(instructions, levels):
            return {"type": "score", "instructions": instructions, "criteria": list(levels)}
        case BinaryQuestion(instructions):
            return {"type": "binary", "instructions": instructions}


def request_fingerprint(request: DecisionRequest, model: str) -> str:
    payload = {
        "model": model,
        "tier": request.tier.value,
        "state": request.state,
        "questions": {k: _question_json(q) for k, q in request.questions.items()},
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
