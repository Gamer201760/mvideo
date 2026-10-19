from datetime import UTC, datetime

import pytest

from app.domain.review import (
    InvalidCorrection,
    ReviewAction,
    ReviewAlreadyResolved,
    ReviewItem,
    ReviewStatus,
    alias_entry,
    evidence_form,
    resolve,
)

NOW = datetime(2026, 10, 14, tzinfo=UTC)


def item() -> ReviewItem:
    return ReviewItem(
        id="1",
        card_key="k",
        category_id=761,
        title="t",
        attribute="Цвет",
        value="алый",
        confidence=0.2,
        source="dictionary",
        evidence="Алый",
        status=ReviewStatus.PENDING,
        resolved_value=None,
        created_at=NOW,
        resolved_at=None,
    )


def test_accept_keeps_value_and_records_alias() -> None:
    resolved, alias = resolve(item(), ReviewAction.ACCEPT, None, NOW)

    assert alias is not None
    assert (resolved.status, resolved.resolved_value) == (ReviewStatus.ACCEPTED, "алый")
    assert (alias.attribute, alias.evidence, alias.value) == ("Цвет", "Алый", "алый")


def test_correct_needs_value_and_cannot_repeat() -> None:
    with pytest.raises(InvalidCorrection):
        resolve(item(), ReviewAction.CORRECT, "  ", NOW)
    resolved, alias = resolve(item(), ReviewAction.CORRECT, " красный ", NOW)

    assert alias is not None
    assert (resolved.status, alias.value) == (ReviewStatus.CORRECTED, "красный")
    with pytest.raises(ReviewAlreadyResolved):
        resolve(resolved, ReviewAction.ACCEPT, None, NOW)


def test_alias_becomes_lexicon_entry_with_canonical_key() -> None:
    _, alias = resolve(item(), ReviewAction.CORRECT, "Красный", NOW)

    assert alias is not None
    entry = alias_entry(alias, numeric=False)

    assert (entry.tokens, entry.key, entry.display) == (("красный",), "красный", "Красный")
    assert evidence_form("  Ёлочный   ЗЕЛЁНЫЙ ") == "елочный зеленый"


def test_manual_override_requires_the_current_confirmed_value() -> None:
    accepted, _ = resolve(item(), ReviewAction.ACCEPT, None, NOW)
    with pytest.raises(ReviewAlreadyResolved):
        resolve(accepted, ReviewAction.CORRECT, "синий", NOW)
    with pytest.raises(ReviewAlreadyResolved):
        resolve(
            accepted,
            ReviewAction.CORRECT,
            "синий",
            NOW,
            override=True,
            expected_value="устаревшее значение",
        )
    updated, alias = resolve(
        accepted,
        ReviewAction.CORRECT,
        "синий",
        NOW,
        override=True,
        expected_value="алый",
    )
    assert alias is not None
    assert accepted.resolved_value == "алый"
    assert updated.resolved_value == alias.value == "синий"
    assert updated.status is ReviewStatus.CORRECTED


def test_reject_keeps_the_rejected_value_and_does_not_create_an_alias() -> None:
    corrected, _ = resolve(item(), ReviewAction.CORRECT, "синий", NOW)
    rejected, alias = resolve(
        corrected, ReviewAction.REJECT, None, NOW, override=True, expected_value="синий"
    )
    assert rejected.status is ReviewStatus.REJECTED
    assert rejected.value == "синий" and rejected.resolved_value is None
    assert alias is None
    restored, alias = resolve(
        rejected, ReviewAction.CORRECT, "синий", NOW, override=True, expected_value=None
    )
    assert restored.status is ReviewStatus.CORRECTED
    assert alias is not None and alias.value == "синий"
