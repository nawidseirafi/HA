import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import yaml
from backend.paths import API_DIR, API_CONFIG_PATH, ENV_PATH


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file) or {}


def _load_env_files() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        values[key.strip()] = raw_value.strip().strip("\"'")
    return values


def _resolve_path(base: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _path_info(base: Path, value: str | None) -> dict[str, Any]:
    path = _resolve_path(base, value)
    if path is None:
        return {"path": "", "exists": False}
    return {"path": str(path), "exists": path.exists()}


def _env_present(name: str | None, env_values: dict[str, str]) -> bool:
    if not name:
        return False
    value = os.getenv(name) or os.getenv(name.upper()) or env_values.get(name) or env_values.get(name.upper())
    return bool(value)


def _setting_present(value: str | None, env_values: dict[str, str]) -> bool:
    if not value:
        return False
    if value in env_values or value.upper() in env_values or os.getenv(value) or os.getenv(value.upper()):
        return True
    placeholders = {"HA_TOKEN", "GEMINI_API_KEY", "OPENAI_API_KEY", "CLAUDE_API_KEY", "MY_WELLNESS_KEY", "MY_WELLNESS_FACILITY_ID"}
    return value not in placeholders and not value.endswith("_KEY") and not value.endswith("_TOKEN")


def _llm_info(config: dict[str, Any], env_values: dict[str, str]) -> dict[str, Any]:
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "")
    provider_config = llm_config.get(provider, {}) if provider else {}
    api_key_setting = provider_config.get("api_key")
    return {
        "provider": provider,
        "model": provider_config.get("model", ""),
        "api_key_configured": _setting_present(api_key_setting, env_values),
    }


def _mywellness_runtime_settings(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {}
    try:
        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                select enabled, prepare_enabled, booking_enabled, prepare_time, booking_time, days, desired_courses
                from mywellness_settings
                where id = 1
                """
            ).fetchone()
    except sqlite3.Error:
        return {}
    if row is None:
        return {}
    try:
        desired_courses = json.loads(row["desired_courses"] or "[]")
    except (TypeError, json.JSONDecodeError):
        desired_courses = []
    return {
        "enabled": bool(row["enabled"]),
        "prepare_enabled": bool(row["prepare_enabled"]),
        "booking_enabled": bool(row["booking_enabled"]),
        "days": int(row["days"] or 2),
        "schedule": [row["prepare_time"], row["booking_time"]],
        "desired_courses": desired_courses if isinstance(desired_courses, list) else [],
        "source": "database",
    }


def _invoice_runtime_settings(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {}
    try:
        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                select enabled, schedule_json
                from invoice_agent_settings
                where id = 1
                """
            ).fetchone()
    except sqlite3.Error:
        return {}
    if row is None:
        return {}
    try:
        schedule = yaml.safe_load(row["schedule_json"] or "[]")
    except yaml.YAMLError:
        schedule = []
    return {
        "enabled": bool(row["enabled"]),
        "schedule": schedule if isinstance(schedule, list) else [],
        "source": "database",
    }


def get_settings() -> dict[str, Any]:
    config = _load_yaml(API_CONFIG_PATH)
    env_values = _load_env_files()

    server_config = config.get("server", {})
    auth_config = config.get("auth", {})
    agents_config = config.get("agents", {})
    invoice_config = agents_config.get("invoices", {})
    mywellness_config = agents_config.get("my_wellness", {})
    market_config = agents_config.get("market", {})
    ha_config = config.get("home_assistant", {})
    ha_notification_config = invoice_config.get("home_assistant_notifications", {})

    token_ttl_seconds = int(auth_config.get("token_ttl_seconds", 0) or 0)
    data_dir = API_DIR / "data"

    mywellness_db = _resolve_path(API_DIR, mywellness_config.get("database_path", data_dir / "mywellness" / "mywellness.db"))
    mywellness_runtime = _mywellness_runtime_settings(mywellness_db) if mywellness_db else {}
    invoice_db_path = _resolve_path(API_DIR, invoice_config.get("database_path", data_dir / "invoices" / "invoices.db"))
    invoice_db = {"path": str(invoice_db_path), "exists": invoice_db_path.exists() if invoice_db_path else False}
    invoice_runtime = _invoice_runtime_settings(invoice_db_path) if invoice_db_path else {}

    return {
        "api": {
            "title": "RoboterSteve Agent API",
            "version": "0.2.0",
            "host": server_config.get("host", "0.0.0.0"),
            "port": server_config.get("port", 8080),
            "config_file": str(API_CONFIG_PATH),
        },
        "auth": {
            "mode": "JWT",
            "enabled": True,
            "username_env": auth_config.get("username_env", "AGENT_API_USERNAME"),
            "password_configured": _env_present(auth_config.get("password_env", "AGENT_API_PASSWORD"), env_values),
            "jwt_secret_configured": _env_present(auth_config.get("jwt_secret_env", "AGENT_API_JWT_SECRET"), env_values),
            "token_ttl_seconds": token_ttl_seconds,
            "token_ttl_days": round(token_ttl_seconds / 86400, 1) if token_ttl_seconds else 0,
        },
        "frontend": {
            "dev_server": "Vite 5173",
            "production_dist": str(API_DIR / "frontend" / "dist"),
            "production_dist_exists": (API_DIR / "frontend" / "dist").exists(),
        },
        "storage": {
            "uploads": _path_info(API_DIR, invoice_config.get("uploads_dir")),
            "log_file": _path_info(API_DIR, config.get("logging", {}).get("file")),
        },
        "agents": {
            "invoices": {
                "enabled": bool(invoice_runtime.get("enabled", invoice_config.get("enabled", True))),
                "upload_dir": _path_info(API_DIR, invoice_config.get("upload_dir")),
                "database": invoice_db,
                "schedule": invoice_runtime.get("schedule", invoice_config.get("schedule", [])),
                "email_enabled": bool(invoice_config.get("email", {}).get("enabled", False)),
                "portal_import_enabled": bool(invoice_config.get("portals", {}).get("enabled", False)),
                "ai_extraction_enabled": bool(invoice_config.get("ai_extraction", {}).get("enabled", False)),
                "poll_interval_seconds": invoice_config.get("poll_interval_seconds"),
            },
            "mywellness": {
                "enabled": bool(mywellness_runtime.get("enabled", mywellness_config.get("enabled", False))),
                "database": {"path": str(mywellness_db), "exists": mywellness_db.exists() if mywellness_db else False},
                "days": mywellness_runtime.get("days", mywellness_config.get("days", 2)),
                "schedule": mywellness_runtime.get("schedule", mywellness_config.get("schedule", [])),
                "desired_courses": mywellness_runtime.get("desired_courses", mywellness_config.get("desired_courses", [])),
                "token_configured": _env_present(mywellness_config.get("token"), env_values),
                "user_id_configured": _env_present(mywellness_config.get("user_id"), env_values),
                "facility_id_configured": _env_present(mywellness_config.get("facility_id"), env_values),
            },
            "vacation": {
                "enabled": bool(agents_config.get("vacation", {}).get("enabled", False)),
            },
            "market": {
                "enabled": bool(market_config.get("enabled", False)),
                "database": _path_info(API_DIR, market_config.get("database_path", data_dir / "market" / "market.db")),
                "price_provider": market_config.get("price_provider", "yahoo"),
                "news_provider": market_config.get("news_provider", "fallback"),
                "trading_enabled": False,
                "disclaimer": "Keine Finanzberatung.",
            },
        },
        "integrations": {
            "llm": _llm_info(config, env_values),
            "home_assistant": {
                "configured": _setting_present(ha_config.get("token"), env_values),
                "notifications_enabled": bool(ha_notification_config.get("enabled", False)),
                "notify_service": ha_notification_config.get("notify_service", ""),
                "persistent_notifications": bool(ha_notification_config.get("persistent", False)),
            },
        },
        "security": {
            "secrets_visible": False,
            "note": "Secrets werden nur als gesetzt/nicht gesetzt angezeigt.",
        },
    }
