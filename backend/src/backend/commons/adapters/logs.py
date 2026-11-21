"""One cached, structured logger for the whole process — ARCHITECTURE.md §17.2. Never
`logging.getLogger(__name__)` per file; every module does `_LOGGER = logs.get_logger()`."""

import contextvars
import json
import logging
import os
import sys
from typing import Any

_logger: logging.Logger | None = None
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        request_id = request_id_var.get()
        if request_id is not None:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        _logger = logging.getLogger(os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "local"))
        _logger.propagate = False
        _logger.setLevel(logging.INFO)
        handler.setLevel(logging.INFO)
        _logger.addHandler(handler)
    return _logger
