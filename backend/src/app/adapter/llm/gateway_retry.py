import math
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class GatewayRetry:
    max_attempts: int = 2
    base_delay_s: float = 0.25
    max_delay_s: float = 2

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 4:
            raise ValueError("Gateway attempts must be between one and four")
        if not all(math.isfinite(v) and v >= 0 for v in (self.base_delay_s, self.max_delay_s)):
            raise ValueError("Gateway retry delays must be finite and nonnegative")
        if max(self.base_delay_s, self.max_delay_s) > 10:
            raise ValueError("Gateway retry delay cannot exceed ten seconds")

    def delay(self, attempt: int, retry_after: str | None) -> float:
        delay = math.ldexp(self.base_delay_s, min(max(attempt - 1, 0), 3))
        if retry_after is not None:
            try:
                requested = float(retry_after)
            except ValueError:
                try:
                    date = parsedate_to_datetime(retry_after)
                    date = date.replace(tzinfo=UTC) if date.tzinfo is None else date
                    requested = (date - datetime.now(UTC)).total_seconds()
                except (ValueError, TypeError, OverflowError):
                    requested = delay
            if math.isfinite(requested):
                delay = max(0, requested)
        return min(delay, self.max_delay_s)
