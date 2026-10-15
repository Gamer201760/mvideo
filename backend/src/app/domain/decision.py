from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.errors import InvalidQuestion
from app.domain.inference import Tier, Usage

type DecisionState = str | Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ChoiceQuestion:
    instructions: str
    options: Mapping[str, str]

    def __post_init__(self) -> None:
        if len(self.options) < 2:
            raise InvalidQuestion("Choice question needs at least two options")


@dataclass(frozen=True, slots=True)
class ScoreQuestion:
    instructions: str
    levels: Sequence[str]

    def __post_init__(self) -> None:
        if len(self.levels) < 2:
            raise InvalidQuestion("Score question needs at least two levels")


@dataclass(frozen=True, slots=True)
class BinaryQuestion:
    instructions: str


type Question = ChoiceQuestion | ScoreQuestion | BinaryQuestion


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    state: DecisionState
    questions: Mapping[str, Question]
    tier: Tier = Tier.FAST

    def __post_init__(self) -> None:
        if not self.questions:
            raise InvalidQuestion("Decision request needs at least one question")


@dataclass(frozen=True, slots=True)
class ChoiceAnswer:
    choice: str
    confidence: float
    probabilities: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class ScoreAnswer:
    score: float
    confidence: float
    probabilities: Sequence[float]


@dataclass(frozen=True, slots=True)
class BinaryAnswer:
    probability: float


type Answer = ChoiceAnswer | ScoreAnswer | BinaryAnswer


@dataclass(frozen=True, slots=True)
class Decision:
    answers: Mapping[str, Answer]
    usage: Usage
