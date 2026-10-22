from dataclasses import dataclass

from app.domain.inference import Usage


@dataclass(frozen=True, slots=True)
class CatalogField:
    attribute: str
    kind: str
    unit: str
    values: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CatalogCandidate:
    category_id: int
    path: str
    score: float
    fields: tuple[CatalogField, ...]
    example_text: str = ""
    example_values: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class FlowCard:
    sku_id: int
    text: str
    candidates: tuple[CatalogCandidate, ...]
    rules: tuple["FieldAnswer", ...] = ()


@dataclass(frozen=True, slots=True)
class TrainProduct:
    sku_id: int
    category_id: int
    text: str
    values: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class FieldAnswer:
    attribute: str
    status: str
    value: str
    unit: str
    quote: str
    start: int = -1
    end: int = -1
    normalized_value: str | None = None
    normalized_unit: str | None = None
    source: str = "hybrid"
    risks: int = 0


@dataclass(frozen=True, slots=True)
class EvidenceRejection:
    attribute: str
    reason: str
    quote: str


@dataclass(frozen=True, slots=True)
class Extraction:
    sku_id: int
    category_id: int | None
    items: tuple[FieldAnswer, ...]
    extra_fields: tuple[FieldAnswer, ...]
    review: bool
    validation_errors: tuple[str, ...] = ()
    proposed_category: str | None = None
    rejections: tuple[EvidenceRejection, ...] = ()
    fallback_reason: str | None = None


@dataclass(frozen=True, slots=True)
class FlowCall:
    stage: str
    sku_ids: tuple[int, ...]
    queue_ms: float
    wall_ms: float
    usage: Usage | None
    error: str | None = None
    dispatched: bool = True
    attempts: int = 1


@dataclass(frozen=True, slots=True)
class FlowOutcome:
    initial: tuple[Extraction, ...]
    final: tuple[Extraction, ...]
    calls: tuple[FlowCall, ...]
    first_ready_ms: float
    final_ready_ms: float


def identifiers(cards: tuple[FlowCard, ...]) -> tuple[list[str], list[int]]:
    fields = list(
        dict.fromkeys(
            field.attribute
            for card in cards
            for candidate in card.candidates
            for field in candidate.fields
        )
    )
    categories = list(dict.fromkeys(c.category_id for card in cards for c in card.candidates))
    return fields, categories
