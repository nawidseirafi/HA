from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from backend.paths import AGENTS_DIR, API_CONFIG_PATH, API_DIR

AGENT_CONFIG_SECTIONS = {
    "invoices": "invoices",
    "market": "market",
    "mywellness": "my_wellness",
    "vacation": "vacation",
}


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file) or {}
    return data if isinstance(data, dict) else {}


def load_global_config() -> dict[str, Any]:
    return read_yaml(API_CONFIG_PATH)


def load_agent_config(agent_id: str) -> dict[str, Any]:
    return read_yaml(AGENTS_DIR / agent_id / "config.yaml")


def load_agent_section(agent_id: str, section: str | None = None) -> dict[str, Any]:
    section_name = section or AGENT_CONFIG_SECTIONS.get(agent_id, agent_id)
    config = load_agent_config(agent_id)
    value = config.get(section_name, {})
    return value if isinstance(value, dict) else {}


def load_agent_runtime_config(agent_id: str) -> dict[str, Any]:
    """Global config plus the agent's own config, without legacy global agents.* values."""
    config = deepcopy(load_global_config())
    config.pop("agents", None)
    config.update(load_agent_config(agent_id))
    return config


def resolve_api_path(value: Any, default: Path | str) -> Path:
    raw = value if value is not None else default
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return (API_DIR / path).resolve()
