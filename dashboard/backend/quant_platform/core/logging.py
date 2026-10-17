"""Application logging setup."""

from __future__ import annotations

import logging
from pathlib import Path

from quant_platform.core.diagnostics import redact_text


class RedactingFormatter(logging.Formatter):
    """Scrub the complete formatted record, including exception tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


def configure_logging(log_dir: str | Path = "logs", level: int = logging.INFO) -> None:
    """Configure console and rotating-per-run file logging."""

    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
        logging.FileHandler(directory / "quant_platform.log", encoding="utf-8"),
    ]
    logging.basicConfig(
        level=level,
        format=(
            "%(asctime)s %(levelname)s %(name)s "
            "task=%(task_name)s strategy=%(strategy_id)s trade_date=%(trade_date)s "
            "order=%(order_id)s %(message)s"
        ),
        handlers=handlers,
        force=True,
    )
    for handler in handlers:
        handler.setFormatter(
            RedactingFormatter(
                "%(asctime)s %(levelname)s %(name)s "
                "task=%(task_name)s strategy=%(strategy_id)s trade_date=%(trade_date)s "
                "order=%(order_id)s %(message)s"
            )
        )
    old_factory = logging.getLogRecordFactory()

    def factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = old_factory(*args, **kwargs)
        defaults = {
            "task_name": "-",
            "strategy_id": "-",
            "trade_date": "-",
            "order_id": "-",
        }
        for name, value in defaults.items():
            if not hasattr(record, name):
                setattr(record, name, value)
        return record

    logging.setLogRecordFactory(factory)
