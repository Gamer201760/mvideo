import pytest

from app.settings import load_settings


@pytest.mark.parametrize(
    ("value", "enabled"), [("true", True), ("false", False), ("1", True), ("0", False)]
)
def test_rule_routing_can_be_enabled_or_disabled(
    monkeypatch: pytest.MonkeyPatch, value: str, enabled: bool
) -> None:
    monkeypatch.setenv("RULES_FIRST", value)
    assert load_settings().rules_first is enabled


def test_invalid_rule_routing_setting_fails_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RULES_FIRST", "maybe")
    with pytest.raises(ValueError, match="RULES_FIRST"):
        load_settings()
