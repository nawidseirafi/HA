import logging
from pathlib import Path
from typing import Any

from backend.config import load_global_config, resolve_api_path


DEFAULT_LOG_FILE = "./logs/agent-api.log"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def configured_log_path(config: dict[str, Any] | None = None) -> Path:
    active_config = config if config is not None else load_global_config()
    logging_config = active_config.get("logging") or {}
    return resolve_api_path(logging_config.get("file"), DEFAULT_LOG_FILE)


def configured_log_level(config: dict[str, Any] | None = None) -> int:
    active_config = config if config is not None else load_global_config()
    logging_config = active_config.get("logging") or {}
    raw_level = str(logging_config.get("level") or "INFO").upper()
    level = getattr(logging, raw_level, logging.INFO)
    return level if isinstance(level, int) else logging.INFO


def configure_logging(config: dict[str, Any] | None = None) -> Path:
    log_path = configured_log_path(config)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    level = configured_log_level(config)

    root = logging.getLogger()
    root.setLevel(level)

    resolved_log_path = log_path.resolve()
    formatter = logging.Formatter(LOG_FORMAT)

    for handler in list(root.handlers):
        if getattr(handler, "_robotersteve_central_log", False):
            root.removeHandler(handler)
            handler.close()

    file_handler = logging.FileHandler(resolved_log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    file_handler._robotersteve_central_log = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    logging.captureWarnings(True)
    return resolved_log_path
