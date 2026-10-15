import math
import re
import time
from collections.abc import Iterator, Mapping, Sequence

from app.domain.decision import (
    Answer,
    BinaryAnswer,
    BinaryQuestion,
    ChoiceAnswer,
    ChoiceQuestion,
    Decision,
    DecisionRequest,
    Question,
    ScoreAnswer,
    ScoreQuestion,
)
from app.domain.inference import Usage

MODEL_NAME = "lexical-overlap"
STEM_LENGTH = 5
MIN_TOKEN_LENGTH = 3
WORD = re.compile(r"\w+")
STOP_WORDS = frozenset(
    {
        "about",
        "does",
        "from",
        "have",
        "should",
        "that",
        "the",
        "this",
        "what",
        "which",
        "with",
        "will",
        "would",
        "and",
        "for",
        "are",
        "how",
        "was",
        "who",
        "why",
        "это",
        "этот",
        "эта",
        "какой",
        "какая",
        "какое",
        "какие",
        "или",
        "что",
        "кто",
        "как",
        "для",
        "про",
        "при",
        "есть",
        "нужно",
        "надо",
        "его",
        "она",
        "они",
    }
)


class LexicalDecisionModel:
    async def decide(self, request: DecisionRequest) -> Decision:
        started = time.perf_counter()
        state = _stems(" ".join(_texts(request.state)))
        answers = {key: _answer(question, state) for key, question in request.questions.items()}
        duration_ms = round((time.perf_counter() - started) * 1000)
        return Decision(answers=answers, usage=Usage(model=MODEL_NAME, duration_ms=duration_ms))

    async def aclose(self) -> None:
        return None


def _answer(question: Question, state: frozenset[str]) -> Answer:
    match question:
        case ChoiceQuestion(_, options):
            names = list(options)
            weights = _softmax([_overlap(f"{name} {options[name]}", state) for name in names])
            best = max(range(len(names)), key=lambda index: weights[index])
            return ChoiceAnswer(
                choice=names[best],
                confidence=weights[best],
                probabilities=dict(zip(names, weights, strict=True)),
            )
        case ScoreQuestion(_, levels):
            weights = _softmax([_overlap(level, state) for level in levels])
            return ScoreAnswer(
                score=sum(level * weight for level, weight in enumerate(weights)),
                confidence=max(weights),
                probabilities=tuple(weights),
            )
        case BinaryQuestion(instructions):
            return BinaryAnswer(probability=_sigmoid(2 * _overlap(instructions, state) - 1))


def _texts(state: object) -> Iterator[str]:
    if isinstance(state, str):
        yield state
    elif isinstance(state, Mapping):
        for value in state.values():
            yield from _texts(value)
    elif isinstance(state, list | tuple):
        for item in state:
            yield from _texts(item)
    elif isinstance(state, int | float):
        yield str(state)


def _stems(text: str) -> frozenset[str]:
    words = (word.lower().replace("ё", "е") for word in WORD.findall(text))
    return frozenset(
        word[:STEM_LENGTH]
        for word in words
        if len(word) >= MIN_TOKEN_LENGTH and word not in STOP_WORDS
    )


def _overlap(text: str, state: frozenset[str]) -> int:
    return len(_stems(text) & state)


def _softmax(scores: Sequence[int]) -> list[float]:
    peak = max(scores)
    exps = [math.exp(score - peak) for score in scores]
    total = sum(exps)
    return [value / total for value in exps]


def _sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-value))
