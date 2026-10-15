import logging

from app.usecase.interface import LogValue


class StdlibLogger:
    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def info(self, event: str, **fields: LogValue) -> None:
        self._log(logging.INFO, event, fields)

    def warning(self, event: str, **fields: LogValue) -> None:
        self._log(logging.WARNING, event, fields)

    def error(self, event: str, *, exc: BaseException | None = None, **fields: LogValue) -> None:
        self._log(logging.ERROR, event, fields, exc)

    def _log(
        self,
        level: int,
        event: str,
        fields: dict[str, LogValue],
        exc: BaseException | None = None,
    ) -> None:
        if not self._logger.isEnabledFor(level):
            return
        pairs = " ".join(f"{key}={value!r}" for key, value in fields.items())
        message = f"{event} {pairs}" if pairs else event
        self._logger.log(level, message, exc_info=exc)


def configure(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(name)s %(message)s")
