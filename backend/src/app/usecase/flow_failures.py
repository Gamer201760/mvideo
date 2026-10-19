from collections.abc import Sequence

from app.domain.attribute_flow import FlowCall
from app.domain.errors import (
    InvalidModelOutput,
    ModelCapacity,
    ModelFailure,
    ModelInputTooLarge,
    ModelRateLimited,
    ModelTimeout,
    ModelUnavailable,
)


def flow_failure(calls: Sequence[FlowCall]) -> ModelFailure:
    errors = {call.error for call in calls}
    if "capacity" in errors:
        return ModelCapacity()
    if "TimeoutError" in errors:
        return ModelTimeout()
    if "input_too_large" in errors:
        return ModelInputTooLarge()
    if errors & {"TypeError", "ValueError"}:
        return InvalidModelOutput()
    for failure in (
        ModelCapacity,
        ModelTimeout,
        ModelRateLimited,
        ModelUnavailable,
        InvalidModelOutput,
        ModelInputTooLarge,
    ):
        if failure.__name__ in errors or failure.code in errors:
            return failure()
    return ModelFailure()
