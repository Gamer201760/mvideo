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
    attempts = sum(call.attempts for call in calls if call.dispatched)
    if "capacity" in errors:
        return ModelCapacity(attempts=attempts)
    if "TimeoutError" in errors:
        return ModelTimeout(attempts=attempts)
    if "input_too_large" in errors:
        return ModelInputTooLarge(attempts=attempts)
    if errors & {"TypeError", "ValueError"}:
        return InvalidModelOutput(attempts=attempts)
    for failure in (
        ModelCapacity,
        ModelTimeout,
        ModelRateLimited,
        ModelUnavailable,
        InvalidModelOutput,
        ModelInputTooLarge,
    ):
        if failure.__name__ in errors or failure.code in errors:
            return failure(attempts=attempts)
    return ModelFailure(attempts=attempts)
