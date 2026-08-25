"""Structured JSON logs for authorize outcomes."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from payment_platform.observability.redact import redact_text


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact_text(record.getMessage()),
        }
        for key in (
            "http_status",
            "transaction_id",
            "state",
            "latency_ms",
            "path",
        ):
            if hasattr(record, key):
                value = getattr(record, key)
                payload[key] = redact_text(value) if isinstance(value, str) else value
        if record.exc_info:
            payload["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_json_logging() -> logging.Logger:
    logger = logging.getLogger("payment_platform")
    if not any(isinstance(handler.formatter, JsonLogFormatter) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
