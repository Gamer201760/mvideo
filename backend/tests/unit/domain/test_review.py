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
    return ReviewItem(id="1", card_key="k", category_id=761, title="t", attribute="Цвет",
                      value="алый", confidence=0.2, source="dictionary", evidence="Алый",
                      status=ReviewStatus.PENDING, resolved_value=None, created_at=NOW,
                      resolved_at=None)


def test_accept_keeps_value_and_records_alias() -> None:
    resolved, alias = resolve(item(), ReviewAction.ACCEPT, None, NOW)

    assert (resolved.status, resolved.resolved_value) == (ReviewStatus.ACCEPTED, "алый")
    assert (alias.attribute, alias.evidence, alias.value) == ("Цвет", "Алый", "алый")


def test_correct_needs_value_and_cannot_repeat() -> None:
    with pytest.raises(InvalidCorrection):
        resolve(item(), ReviewAction.CORRECT, "  ", NOW)
    resolved, alias = resolve(item(), ReviewAction.CORRECT, " красный ", NOW)

    assert (resolved.status, alias.value) == (ReviewStatus.CORRECTED, "красный")
    with pytest.raises(ReviewAlreadyResolved):
        resolve(resolved, ReviewAction.ACCEPT, None, NOW)


def test_alias_becomes_lexicon_entry_with_canonical_key() -> None:
    _, alias = resolve(item(), ReviewAction.CORRECT, "Красный", NOW)

    entry = alias_entry(alias, numeric=False)

    assert (entry.tokens, entry.key, entry.display) == (("красный",), "красный", "Красный")
    assert evidence_form("  Ёлочный   ЗЕЛЁНЫЙ ") == "елочный зеленый"
