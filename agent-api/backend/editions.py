import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from backend.config import load_global_config
from backend.paths import API_DIR


DEFAULT_EDITION = "personal"
EDITIONS_DIR = API_DIR / "editions"
EDITION_LOCK_PATH = EDITIONS_DIR / "edition.lock"
DEFAULT_PERSONAL_AGENTS = ("scheduler", "invoices", "market", "mywellness", "vacation")
DEFAULT_PERSONAL_CORE_SERVICES = (
    "auth",
    "system",
    "settings",
    "messaging",
    "orchestrator",
    "homeassistant",
    "household",
    "infrastructure",
    "waste",
    "llm",
)


@dataclass(frozen=True)
class Edition:
    name: str
    description: str
    enabled_agents: tuple[str, ...]
    enabled_core_services: tuple[str, ...]
    frontend_app: str
    include_frontend: bool
    include_data: bool
    include_files: tuple[str, ...]
    exclude_files: tuple[str, ...]
    config_template: str
    source_path: Path | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "enabled_agents": list(self.enabled_agents),
            "enabled_core_services": list(self.enabled_core_services),
            "frontend_app": self.frontend_app,
        }


def active_edition_name() -> str:
    env_value = os.getenv("ROBOTERSTEVE_EDITION", "").strip()
    if env_value:
        return env_value
    locked = locked_edition_name()
    if locked:
        return locked
    config = load_global_config()
    edition = config.get("edition") if isinstance(config.get("edition"), dict) else {}
    config_value = str(edition.get("name") or "").strip()
    return config_value or DEFAULT_EDITION


@lru_cache(maxsize=16)
def load_edition(name: str | None = None) -> Edition:
    edition_name = (name or active_edition_name() or DEFAULT_EDITION).strip()
    path = EDITIONS_DIR / f"{edition_name}.yaml"
    if not path.exists():
        if locked_edition_name():
            raise RuntimeError(f"Edition '{edition_name}' is locked but not available in {EDITIONS_DIR}.")
        if edition_name != DEFAULT_EDITION:
            return load_edition(DEFAULT_EDITION)
        return _default_personal_edition()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        if locked_edition_name():
            raise RuntimeError(f"Edition '{edition_name}' could not be loaded from {path}.")
        if edition_name != DEFAULT_EDITION:
            return load_edition(DEFAULT_EDITION)
        return _default_personal_edition()
    return _edition_from_data(data, path)


def active_edition() -> Edition:
    return load_edition(active_edition_name())


def is_agent_enabled_for_active_edition(agent_id: str) -> bool:
    edition = active_edition()
    return agent_id in set(edition.enabled_agents)


def is_core_service_enabled(service_id: str) -> bool:
    edition = active_edition()
    return service_id in set(edition.enabled_core_services)


def locked_edition_name() -> str | None:
    try:
        value = EDITION_LOCK_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _edition_from_data(data: dict[str, Any], path: Path) -> Edition:
    name = str(data.get("name") or path.stem).strip() or path.stem
    enabled_agents = _string_tuple(data.get("enabled_agents"))
    enabled_core_services = _string_tuple(data.get("enabled_core_services"))
    return Edition(
        name=name,
        description=str(data.get("description") or ""),
        enabled_agents=enabled_agents,
        enabled_core_services=enabled_core_services,
        frontend_app=str(data.get("frontend_app") or name),
        include_frontend=bool(data.get("include_frontend", True)),
        include_data=bool(data.get("include_data", False)),
        include_files=_string_tuple(data.get("include_files")),
        exclude_files=_string_tuple(data.get("exclude_files")),
        config_template=str(data.get("config_template") or name),
        source_path=path,
    )


def _empty_edition(name: str) -> Edition:
    return Edition(
        name=name,
        description="",
        enabled_agents=(),
        enabled_core_services=(),
        frontend_app=name,
        include_frontend=True,
        include_data=False,
        include_files=(),
        exclude_files=(),
        config_template=name,
    )


def _default_personal_edition() -> Edition:
    """Compatibility fallback for development checkouts without edition YAMLs."""
    return Edition(
        name=DEFAULT_EDITION,
        description="Private RoboterSteve Edition",
        enabled_agents=DEFAULT_PERSONAL_AGENTS,
        enabled_core_services=DEFAULT_PERSONAL_CORE_SERVICES,
        frontend_app=DEFAULT_EDITION,
        include_frontend=True,
        include_data=False,
        include_files=(),
        exclude_files=(),
        config_template=DEFAULT_EDITION,
    )


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())
