from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": getattr(record, "service", record.name),
            "level": record.levelname,
            "request_id": getattr(record, "request_id", None),
            "trace_id": getattr(record, "trace_id", None),
            "endpoint": getattr(record, "endpoint", None),
            "status_code": getattr(record, "status_code", None),
            "latency_ms": getattr(record, "latency_ms", None),
            "message": record.getMessage(),
            "metadata": getattr(record, "metadata", {}) or {},
        }
        if record.exc_info:
            payload["metadata"]["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_logger(service: str) -> logging.Logger:
    logger = logging.getLogger(service)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


class JsonLogger:
    """Convenience wrapper that always emits structured JSON logs."""

    def __init__(self, service: str) -> None:
        self.service = service
        self._logger = get_logger(service)

    def log(
        self,
        level: str,
        message: str,
        *,
        request_id: str | None = None,
        trace_id: str | None = None,
        endpoint: str | None = None,
        status_code: int | None = None,
        latency_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        extra = {
            "service": self.service,
            "request_id": request_id,
            "trace_id": trace_id,
            "endpoint": endpoint,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "metadata": metadata or {},
        }
        getattr(self._logger, level.lower(), self._logger.info)(message, extra=extra)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": self.service,
            "level": level.upper(),
            "request_id": request_id,
            "trace_id": trace_id,
            "endpoint": endpoint,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "message": message,
            "metadata": metadata or {},
        }
