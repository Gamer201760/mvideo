import pytest

from app.settings import load_settings


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ACCEPTANCE_THRESHOLD", "nan"),
        ("ACCEPTANCE_THRESHOLD", "1.1"),
        ("AUTO_ACCEPT", "perhaps"),
        ("EXTRACTION_BATCH_SIZE", "0"),
        ("EXTRACTION_BATCH_SIZE", "17"),
        ("EXTRACTION_CONCURRENCY", "9"),
        ("EXTRACTION_MAX_PENDING", "1"),
        ("EXTRACTION_MAX_BATCH_CHARS", "999"),
    ],
)
def test_invalid_scale_configuration_fails_at_startup(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        load_settings()
