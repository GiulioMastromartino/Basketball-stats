import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional

from flask import g, has_request_context, request


class JSONFormatter(logging.Formatter):
    def __init__(self, *, include_exc_info: bool = True):
        super().__init__()
        self.include_exc_info = include_exc_info

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if has_request_context():
            payload["request_id"] = getattr(g, "request_id", None)
            payload["method"] = request.method
            payload["path"] = request.path
            payload["remote_addr"] = request.remote_addr
            if current_user := getattr(g, "user", None):
                payload["user"] = current_user
            elif hasattr(request, "authorization") and request.authorization:
                payload["user"] = request.authorization.get("username")

        exc_info = record.exc_info
        if exc_info and exc_info is not True and self.include_exc_info:
            payload["exception"] = {
                "type": exc_info[0].__name__,
                "message": str(exc_info[1]),
            }
            if record.exc_text:
                payload["traceback"] = record.exc_text

        if hasattr(record, "extra_fields"):
            payload.update(record.extra_fields)

        return json.dumps(payload, default=str, ensure_ascii=False)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if has_request_context():
            record.request_id = getattr(g, "request_id", None)
        else:
            record.request_id = None
        return True


_LOGGER_CACHE: dict[str, logging.Logger] = {}


def get_logger(name: str) -> logging.Logger:
    if name in _LOGGER_CACHE:
        return _LOGGER_CACHE[name]

    logger = logging.getLogger(name)
    logger.addFilter(RequestIdFilter())
    _LOGGER_CACHE[name] = logger
    return logger


def configure_root_logger(
    level: int = logging.INFO,
    fmt: str = "json",
    log_file: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
):
    root = logging.getLogger()
    root.setLevel(level)

    for handler in root.handlers[:]:
        root.removeHandler(handler)

    if fmt == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s]: %(message)s"
        )

    if log_file:
        from logging.handlers import RotatingFileHandler

        handler: logging.Handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count
        )
    else:
        handler = logging.StreamHandler()

    handler.setFormatter(formatter)
    root.addHandler(handler)

    from flask import current_app

    if current_app:
        current_app.logger.handlers[:] = []
        current_app.logger.addHandler(handler)
        current_app.logger.setLevel(level)
