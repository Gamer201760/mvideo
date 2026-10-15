import logging

import pytest

from app.adapter.log.stdlib import StdlibLogger


def test_fields_follow_event(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="test.stdlib")

    StdlibLogger("test.stdlib").info("question_answered", path="/q", count=2, cached=None)

    [record] = caplog.records
    assert record.levelno == logging.INFO
    assert record.getMessage() == "question_answered path='/q' count=2 cached=None"


def test_event_without_fields_is_logged_as_is(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="test.stdlib")

    StdlibLogger("test.stdlib").warning("cache_cold")

    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [
        (logging.WARNING, "cache_cold")
    ]


def test_error_keeps_traceback(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR, logger="test.stdlib")
    error = RuntimeError("boom")

    StdlibLogger("test.stdlib").error("unexpected_error", exc=error, path="/fail")

    [record] = caplog.records
    assert record.exc_info is not None
    assert record.exc_info[1] is error


def test_disabled_level_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="test.stdlib")

    StdlibLogger("test.stdlib").info("ignored")

    assert caplog.records == []
