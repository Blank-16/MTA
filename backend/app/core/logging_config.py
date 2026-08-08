import json
import logging
import sys
import traceback
from typing import Any

from app.core.config import settings


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "loc": f"{record.pathname}:{record.lineno}",
        }
        if record.exc_info:
            payload["exc"] = traceback.format_exception(*record.exc_info)

        skip = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "taskName",
        }
        for k, v in record.__dict__.items():
            if k not in skip:
                payload[k] = v

        return json.dumps(payload, default=str)


class _DevFormatter(logging.Formatter):
    _COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self._COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname:<8}{self._RESET}"
        return super().format(record)


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if settings.is_production:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            _DevFormatter(fmt="%(asctime)s %(levelname)s %(name)s  %(message)s", datefmt="%H:%M:%S")
        )
    root.addHandler(handler)

    for noisy in ("httpcore", "httpx", "openai", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
