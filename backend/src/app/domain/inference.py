from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

type JsonSchema = dict[str, Any]
type Vector = Sequence[float]


class Tier(StrEnum):
    FAST = "fast"
    SMART = "smart"


class Effort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class StructuredRequest:
    system: str
    prompt: str
    schema: JsonSchema
    tier: Tier = Tier.FAST
    effort: Effort | None = None


@dataclass(frozen=True, slots=True)
class Usage:
    model: str
    duration_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


@dataclass(frozen=True, slots=True)
class Completion:
    output: dict[str, Any]
    usage: Usage


def total_cost(*usages: Usage | None) -> float:
    return sum(u.cost_usd or 0 for u in usages if u is not None)
