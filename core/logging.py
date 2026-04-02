"""Application logging setup with JSON output and configurable log level."""

from __future__ import annotations

import contextvars
import logging
import os

from pythonjsonlogger import jsonlogger


_CONFIGURED = False
_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = _request_id_ctx.get()
        return True


def _configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(operation)s %(patient_id)s %(consultation_id)s %(request_id)s"
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    _CONFIGURED = True


def set_request_id(request_id: str) -> contextvars.Token:
    return _request_id_ctx.set(request_id)


def reset_request_id(token: contextvars.Token) -> None:
    _request_id_ctx.reset(token)


def get_logger(name: str, request_id: str | None = None) -> logging.Logger:
    _configure_logging()
    base_logger = logging.getLogger(name)
    if request_id is not None:
        return logging.LoggerAdapter(base_logger, {"request_id": request_id})  # type: ignore[return-value]
    return base_logger