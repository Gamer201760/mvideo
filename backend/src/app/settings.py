from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from app.adapter.decision.system_one import DEFAULT_MODEL_NAME, TYPESAFE_URL

DEFAULT_STAND_PACK = "data/stand/pack.json.gz"
DEFAULT_STAND_MODELS = "data/stand/models"
DEFAULT_TEXT_INDEX = "data/stand/text"
DEFAULT_TEXT_CACHE = "data/cache/text.sqlite"
DEFAULT_EMBEDDINGS_MODEL = "qwen/qwen3-embedding-8b"
DEFAULT_EMBEDDINGS_DIMENSIONS = 512
DEFAULT_LLM_FAST = "anthropic/claude-haiku-5.5"
DEFAULT_LLM_SMART = "anthropic/claude-sonnet-5.5"


class DecisionProvider(StrEnum):
    LEXICAL = "lexical"
    SYSTEM_ONE = "system_one"


class LanguageProvider(StrEnum):
    NONE = "none"
    OPENAI = "openai"


class ConfigError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Settings:
    decision_provider: DecisionProvider = DecisionProvider.LEXICAL
    decision_url: str = TYPESAFE_URL
    decision_api_key: str | None = None
    decision_timeout_s: float = 10.0
    decision_model_name: str = DEFAULT_MODEL_NAME
    language_provider: LanguageProvider = LanguageProvider.NONE
    stand_pack: str = DEFAULT_STAND_PACK
    stand_models: str = DEFAULT_STAND_MODELS
    llm_url: str | None = None
    llm_api_key: str | None = None
    llm_fast_model: str = DEFAULT_LLM_FAST
    llm_smart_model: str = DEFAULT_LLM_SMART
    embeddings_url: str | None = None
    embeddings_api_key: str | None = None
    embeddings_model: str = DEFAULT_EMBEDDINGS_MODEL
    embeddings_dimensions: int = DEFAULT_EMBEDDINGS_DIMENSIONS
    text_index: str = DEFAULT_TEXT_INDEX
    text_cache: str = DEFAULT_TEXT_CACHE


def load_settings(env: Mapping[str, str]) -> Settings:
    return Settings(
        decision_provider=_choice(
            env, "DECISION_MODEL", DecisionProvider, DecisionProvider.LEXICAL
        ),
        decision_url=env.get("DECISION_MODEL_URL") or TYPESAFE_URL,
        decision_api_key=env.get("DECISION_MODEL_API_KEY") or None,
        decision_timeout_s=_positive(env, "DECISION_MODEL_TIMEOUT_S", 10.0),
        decision_model_name=env.get("DECISION_MODEL_NAME") or DEFAULT_MODEL_NAME,
        language_provider=_choice(env, "LANGUAGE_MODEL", LanguageProvider, LanguageProvider.NONE),
        stand_pack=env.get("STAND_PACK") or DEFAULT_STAND_PACK,
        stand_models=env.get("STAND_MODELS") or DEFAULT_STAND_MODELS,
        llm_url=env.get("LLM_URL") or None,
        llm_api_key=env.get("LLM_API_KEY") or None,
        llm_fast_model=env.get("LLM_FAST_MODEL") or DEFAULT_LLM_FAST,
        llm_smart_model=env.get("LLM_SMART_MODEL") or DEFAULT_LLM_SMART,
        embeddings_url=env.get("EMBEDDINGS_URL") or None,
        embeddings_api_key=env.get("EMBEDDINGS_API_KEY") or None,
        embeddings_model=env.get("EMBEDDINGS_MODEL") or DEFAULT_EMBEDDINGS_MODEL,
        embeddings_dimensions=int(_positive(env, "EMBEDDINGS_DIMENSIONS",
                                            DEFAULT_EMBEDDINGS_DIMENSIONS)),
        text_index=env.get("TEXT_INDEX") or DEFAULT_TEXT_INDEX,
        text_cache=env.get("TEXT_CACHE") or DEFAULT_TEXT_CACHE,
    )


def _choice[E: StrEnum](env: Mapping[str, str], name: str, kind: type[E], default: E) -> E:
    raw = env.get(name) or default.value
    try:
        return kind(raw)
    except ValueError:
        allowed = ", ".join(member.value for member in kind)
        raise ConfigError(f"{name}={raw!r} is not supported; use one of: {allowed}") from None


def _positive(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{name}={raw!r} is not a number") from None
    if value <= 0:
        raise ConfigError(f"{name}={raw!r} must be positive")
    return value
