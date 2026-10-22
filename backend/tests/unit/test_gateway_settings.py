import pytest

from app.settings import load_settings


@pytest.fixture(autouse=True)
def isolate_gateway_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "GATEWAY_URL",
        "GATEWAY_API_KEY",
        "GATEWAY_MODEL",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "GATEWAY_FALLBACK",
    ):
        monkeypatch.delenv(name, raising=False)


def test_hackathon_environment_configures_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    settings = load_settings()
    assert settings.gateway_url == "https://example.test/v1"
    assert settings.gateway_key == "test-key"
    assert settings.gateway_model == "test-model"
    assert "test-key" not in repr(settings)


def test_explicit_gateway_settings_override_openai_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in (
        ("URL", "https://example.test/v1"),
        ("API_KEY", "test-key"),
        ("MODEL", "m"),
    ):
        monkeypatch.setenv(f"GATEWAY_{name}", value)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://ignored.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ignored-key")
    monkeypatch.setenv("OPENAI_MODEL", "ignored-model")
    settings = load_settings()
    assert settings.gateway_url == "https://example.test/v1"
    assert settings.gateway_key == "test-key"
    assert settings.gateway_model == "m"


def test_default_gateway_is_preserved_without_hackathon_environment() -> None:
    settings = load_settings()
    assert settings.gateway_url == "https://ai.goatwhistle.ru/v1"
    assert settings.gateway_key == ""
    assert settings.gateway_model == "default"


def test_openai_key_without_explicit_endpoint_keeps_local_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert load_settings().gateway_key == ""


@pytest.mark.parametrize("value", ["true", "1", " TRUE "])
def test_gateway_fallback_can_be_enabled(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("GATEWAY_FALLBACK", value)
    assert load_settings().gateway_fallback is True


@pytest.mark.parametrize("value", ["false", "0", " FALSE "])
def test_gateway_fallback_can_be_disabled(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("GATEWAY_FALLBACK", value)
    assert load_settings().gateway_fallback is False


def test_invalid_gateway_fallback_fails_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_FALLBACK", "sometimes")
    with pytest.raises(ValueError, match="GATEWAY_FALLBACK must be true or false"):
        load_settings()
