import math
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    database: Path = Path("var/app.db")
    gateway_url: str = "https://ai.goatwhistle.ru/v1"
    gateway_key: str = field(default="", repr=False)
    gateway_model: str = "default"
    gateway_timeout: float = 120
    rules_first: bool = True
    batch_size: int = 4
    concurrency: int = 2
    max_batch_chars: int = 48_000
    max_pending: int = 8
    acceptance_threshold: float = 0.95
    auto_accept: bool = True
    gateway_fallback: bool = True

    def __post_init__(self) -> None:
        if not 1 <= self.batch_size <= 16 or not 1 <= self.concurrency <= 8:
            raise ValueError("Batch size must be 1..16 and concurrency 1..8")
        if (
            not 1_000 <= self.max_batch_chars <= 240_000
            or not self.concurrency <= self.max_pending <= 64
        ):
            raise ValueError("Invalid batch character limit or pending capacity")
        if not math.isfinite(self.acceptance_threshold) or not 0 < self.acceptance_threshold <= 1:
            raise ValueError("Acceptance threshold must be greater than zero and at most one")


def boolean_setting(name: str, default: str) -> bool:
    value = os.environ.get(name, default).strip().casefold()
    if value not in {"true", "false", "1", "0"}:
        raise ValueError(f"{name} must be true or false")
    return value in {"true", "1"}


def load_settings() -> Settings:
    timeout = float(os.environ.get("GATEWAY_TIMEOUT_S", "120"))
    if not 1 <= timeout <= 180:
        raise ValueError("GATEWAY_TIMEOUT_S must be between 1 and 180")
    gateway_url = os.environ.get("GATEWAY_URL") or os.environ.get("OPENAI_BASE_URL")
    gateway_key = os.environ.get("GATEWAY_API_KEY") or (
        os.environ.get("OPENAI_API_KEY", "") if gateway_url else ""
    )
    return Settings(
        database=Path(os.environ.get("DATABASE_PATH", "var/app.db")).resolve(),
        gateway_url=gateway_url or "https://ai.goatwhistle.ru/v1",
        gateway_key=gateway_key,
        gateway_model=os.environ.get("GATEWAY_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or "default",
        gateway_timeout=timeout,
        rules_first=boolean_setting("RULES_FIRST", "true"),
        batch_size=int(os.environ.get("EXTRACTION_BATCH_SIZE", "4")),
        concurrency=int(os.environ.get("EXTRACTION_CONCURRENCY", "2")),
        max_batch_chars=int(os.environ.get("EXTRACTION_MAX_BATCH_CHARS", "48000")),
        max_pending=int(os.environ.get("EXTRACTION_MAX_PENDING", "8")),
        acceptance_threshold=float(os.environ.get("ACCEPTANCE_THRESHOLD", "0.95")),
        auto_accept=boolean_setting("AUTO_ACCEPT", "true"),
        gateway_fallback=boolean_setting("GATEWAY_FALLBACK", "true"),
    )
