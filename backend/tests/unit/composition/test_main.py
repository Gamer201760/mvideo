import pytest
from fastapi.testclient import TestClient

from app.adapter.decision.lexical import LexicalDecisionModel
from app.adapter.decision.system_one import SystemOneModel
from app.main import Providers, build_decision_model, build_language_model, create_app
from app.settings import ConfigError, DecisionProvider, LanguageProvider, Settings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("settings", "decision", "language"),
    [
        (Settings(), LexicalDecisionModel, type(None)),
        (
            Settings(decision_provider=DecisionProvider.SYSTEM_ONE),
            SystemOneModel,
            type(None),
        ),
    ],
)
async def test_settings_select_implementations(
    settings: Settings, decision: type, language: type
) -> None:
    decision_model = build_decision_model(settings)

    assert isinstance(decision_model, decision)
    assert isinstance(build_language_model(settings), language)
    await decision_model.aclose()


def test_lifespan_exposes_and_closes_providers() -> None:
    app = create_app(Settings(decision_provider=DecisionProvider.SYSTEM_ONE))

    with TestClient(app):
        providers = app.state.providers
        assert isinstance(providers, Providers)
        assert isinstance(providers.decision, SystemOneModel)
        assert not providers.decision._client.is_closed

    assert providers.decision._client.is_closed


def test_invalid_environment_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECISION_MODEL", "jev")

    with pytest.raises(ConfigError, match="DECISION_MODEL"):
        create_app()


def test_openai_language_model_needs_url_and_key() -> None:
    with pytest.raises(ConfigError, match="LLM_URL and LLM_API_KEY"):
        build_language_model(Settings(language_provider=LanguageProvider.OPENAI))
