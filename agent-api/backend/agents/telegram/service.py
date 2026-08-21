from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

from backend.agents.garden.service import GardenService
from backend.config import load_agent_section, resolve_api_path
from backend.paths import AGENTS_DIR
from backend.services.homeassistant_service import HomeAssistantService
from backend.services.llm.factory import create_llm_client
from backend.services.messaging import MessagingService


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    allowed_chat_ids: tuple[str, ...] = ()
    auto_pair_first_chat: bool = True
    poll_interval_seconds: int = 10
    timeout_seconds: int = 10
    hourly_limit: int = 30
    daily_limit: int = 120
    database_path: str = "data/telegram/telegram.db"


class TelegramApiClient:
    def __init__(self, config: TelegramConfig) -> None:
        self.config = config

    def get_updates(self, offset: int | None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"timeout": self.config.timeout_seconds, "allowed_updates": json.dumps(["message"])}
        if offset is not None:
            params["offset"] = offset
        response = requests.get(self._url("getUpdates"), params=params, timeout=self.config.timeout_seconds + 5)
        response.raise_for_status()
        data = response.json()
        result = data.get("result") if isinstance(data, dict) else None
        return result if isinstance(result, list) else []

    def send_message(self, chat_id: str, text: str) -> dict[str, Any] | None:
        response = requests.post(
            self._url("sendMessage"),
            json={"chat_id": chat_id, "text": text[:4000]},
            timeout=self.config.timeout_seconds + 5,
        )
        response.raise_for_status()
        data = response.json()
        result = data.get("result") if isinstance(data, dict) else None
        return result if isinstance(result, dict) else None

    def get_me(self) -> dict[str, Any]:
        response = requests.get(self._url("getMe"), timeout=self.config.timeout_seconds + 5)
        response.raise_for_status()
        data = response.json()
        result = data.get("result") if isinstance(data, dict) else None
        return result if isinstance(result, dict) else {}

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.config.bot_token}/{method}"


class TelegramStore:
    def __init__(self, database_path: str | Path = "data/telegram/telegram.db") -> None:
        self.database_path = resolve_api_path(database_path, "data/telegram/telegram.db")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def ensure_schema(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """create table if not exists telegram_state (
                    id integer primary key check (id = 1),
                    last_update_id integer not null default 0,
                    updated_at text not null
                )"""
            )
            connection.execute(
                """create table if not exists telegram_messages (
                    id integer primary key autoincrement,
                    update_id integer not null unique,
                    message_id integer,
                    chat_id text not null,
                    question_hash text,
                    status text not null,
                    error text,
                    response_message_id integer,
                    processing_ms integer,
                    received_at text not null,
                    responded_at text,
                    created_at text not null
                )"""
            )
            connection.execute("insert or ignore into telegram_state (id, last_update_id, updated_at) values (1, 0, ?)", (utc_now(),))
            connection.commit()

    def next_offset(self) -> int | None:
        with self.connect() as connection:
            row = connection.execute("select last_update_id from telegram_state where id = 1").fetchone()
        last_update_id = int(row["last_update_id"] if row else 0)
        return last_update_id + 1 if last_update_id else None

    def mark_update(self, update_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "update telegram_state set last_update_id = max(last_update_id, ?), updated_at = ? where id = 1",
                (update_id, utc_now()),
            )
            connection.commit()

    def already_processed(self, update_id: int) -> bool:
        with self.connect() as connection:
            row = connection.execute("select id from telegram_messages where update_id = ?", (update_id,)).fetchone()
        return row is not None

    def rate_limit_exceeded(self, chat_id: str, hourly_limit: int, daily_limit: int) -> bool:
        current = datetime.now(timezone.utc)
        hour_since = (current - timedelta(hours=1)).isoformat(timespec="seconds")
        day_since = (current - timedelta(days=1)).isoformat(timespec="seconds")
        with self.connect() as connection:
            hour = connection.execute(
                """select count(*) as count from telegram_messages
                   where chat_id = ? and received_at >= ? and status not in ('rejected', 'duplicate', 'ignored')""",
                (chat_id, hour_since),
            ).fetchone()
            day = connection.execute(
                """select count(*) as count from telegram_messages
                   where chat_id = ? and received_at >= ? and status not in ('rejected', 'duplicate', 'ignored')""",
                (chat_id, day_since),
            ).fetchone()
        return int(hour["count"] if hour else 0) >= hourly_limit or int(day["count"] if day else 0) >= daily_limit

    def record(
        self,
        *,
        update_id: int,
        message_id: int | None,
        chat_id: str,
        question: str,
        status: str,
        received_at: str,
        error: str | None = None,
        response_message_id: int | None = None,
        processing_ms: int | None = None,
        responded_at: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """insert or ignore into telegram_messages
                   (update_id, message_id, chat_id, question_hash, status, error, response_message_id,
                    processing_ms, received_at, responded_at, created_at)
                   values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    update_id,
                    message_id,
                    chat_id,
                    _question_hash(question) if question else None,
                    status,
                    error,
                    response_message_id,
                    processing_ms,
                    received_at,
                    responded_at,
                    utc_now(),
                ),
            )
            connection.commit()

    def recent_messages(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "select * from telegram_messages order by received_at desc, id desc limit ?",
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        return [dict(row) for row in rows]


class TelegramService:
    agent_id = "telegram"

    def __init__(
        self,
        store: TelegramStore | None = None,
        client: TelegramApiClient | None = None,
        messaging: MessagingService | None = None,
    ) -> None:
        self._store = store
        self._client = client
        self.messaging = messaging or MessagingService()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_error: str | None = None
        self._last_poll_at: str | None = None
        self._last_sent_at: str | None = None

    def config(self) -> TelegramConfig:
        raw = load_agent_section(self.agent_id)
        env_values = _read_env_file()
        token = _resolve_secret(raw.get("bot_token"), env_values)
        allowed = _list_value(raw.get("allowed_chat_ids"))
        allowed.extend(_list_value(os.getenv("TELEGRAM_ALLOWED_CHAT_IDS") or env_values.get("TELEGRAM_ALLOWED_CHAT_IDS")))
        default_chat = str(raw.get("default_chat_id") or os.getenv("TELEGRAM_CHAT_ID") or env_values.get("TELEGRAM_CHAT_ID") or "").strip()
        if default_chat:
            allowed.append(default_chat)
        allowed = _allowed_chat_ids_without_bot_id(allowed, token)
        return TelegramConfig(
            enabled=bool(raw.get("enabled", False)),
            bot_token=token,
            allowed_chat_ids=tuple(dict.fromkeys(chat for chat in allowed if chat)),
            auto_pair_first_chat=bool(raw.get("auto_pair_first_chat", True)),
            poll_interval_seconds=_int_value(raw.get("poll_interval_seconds"), 10, minimum=3),
            timeout_seconds=_int_value(raw.get("timeout_seconds"), 10, minimum=1),
            hourly_limit=_int_value(raw.get("hourly_limit"), 30, minimum=1),
            daily_limit=_int_value(raw.get("daily_limit"), 120, minimum=1),
            database_path=str(raw.get("database_path") or "data/telegram/telegram.db"),
        )

    def status(self) -> dict[str, Any]:
        config = self.config()
        return {
            "agent_id": self.agent_id,
            "enabled": config.enabled,
            "configured": bool(config.bot_token and config.allowed_chat_ids),
            "is_running": self.is_running(),
            "status": "running" if self.is_running() else "disabled" if not config.enabled else "configured",
            "allowed_chat_count": len(config.allowed_chat_ids),
            "last_poll_at": self._last_poll_at,
            "last_sent_at": self._last_sent_at,
            "last_error": self._last_error,
            "recent_messages": self.store(config).recent_messages(limit=10),
        }

    def start_scheduler(self) -> None:
        if self.is_running():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="telegram-agent", daemon=True)
        self._thread.start()

    def stop_scheduler(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None

    def start(self) -> dict[str, Any]:
        self.start_scheduler()
        return self.status()

    def stop(self) -> dict[str, Any]:
        self.stop_scheduler()
        return self.status()

    def enable(self) -> dict[str, Any]:
        self.update_settings({"enabled": True})
        self.start_scheduler()
        return self.status()

    def disable(self) -> dict[str, Any]:
        self.update_settings({"enabled": False})
        self.stop_scheduler()
        return self.status()

    def toggle(self) -> dict[str, Any]:
        return self.disable() if self.config().enabled else self.enable()

    def update_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        current = load_agent_section(self.agent_id)
        next_config = dict(current)
        for key in (
            "enabled",
            "bot_token",
            "allowed_chat_ids",
            "auto_pair_first_chat",
            "default_chat_id",
            "poll_interval_seconds",
            "timeout_seconds",
            "hourly_limit",
            "daily_limit",
            "database_path",
        ):
            if key in settings and settings[key] is not None:
                next_config[key] = settings[key]
        self._write_config(next_config)
        return self.status()

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def poll_once(self) -> dict[str, Any]:
        config = self.config()
        if not config.enabled:
            return {"processed": 0, "skipped": "disabled"}
        if not config.bot_token:
            return {"processed": 0, "skipped": "missing_bot_token"}
        store = self.store(config)
        client = self.client(config)
        updates = client.get_updates(store.next_offset())
        processed = 0
        for update in updates:
            update_id = int(update.get("update_id") or 0)
            try:
                self.process_update(update, config=config)
            finally:
                if update_id:
                    store.mark_update(update_id)
            processed += 1
        self._last_poll_at = utc_now()
        self._last_error = None
        return {"processed": processed}

    def process_update(self, update: dict[str, Any], config: TelegramConfig | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        config = config or self.config()
        store = self.store(config)
        update_id = int(update.get("update_id") or 0)
        message = update.get("message") if isinstance(update.get("message"), dict) else {}
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        from_user = message.get("from") if isinstance(message.get("from"), dict) else {}
        chat_id = str(chat.get("id") or "").strip()
        message_id = int(message.get("message_id") or 0) or None
        received_at = utc_now()
        if not update_id or not chat_id:
            return {"status": "ignored", "error": "invalid_update"}
        if store.already_processed(update_id):
            return {"status": "duplicate"}
        question = _sanitize_question(str(message.get("text") or ""))
        if bool(from_user.get("is_bot")):
            self._record(store, update_id, message_id, chat_id, question, "ignored", "bot_message", started, received_at)
            return {"status": "ignored", "error": "bot_message"}
        if not question:
            self._record(store, update_id, message_id, chat_id, question, "ignored", "empty_message", started, received_at)
            return {"status": "ignored", "error": "empty_message"}
        allowed_chat_ids = _effective_allowed_chat_ids(config)
        if chat_id not in set(allowed_chat_ids):
            if config.auto_pair_first_chat and not allowed_chat_ids:
                self.update_settings({"allowed_chat_ids": [chat_id], "default_chat_id": chat_id})
                config = self.config()
                self._send(config, chat_id, "Dieser Telegram-Chat ist jetzt mit Roboter Steve verbunden.")
            else:
                self._send(config, chat_id, "Dieser Telegram-Chat ist nicht für Roboter Steve freigeschaltet.")
                self._record(store, update_id, message_id, chat_id, question, "rejected", "unknown_chat", started, received_at)
                return {"status": "rejected", "error": "unknown_chat"}
        if store.rate_limit_exceeded(chat_id, config.hourly_limit, config.daily_limit):
            self._send(config, chat_id, "Das Telegram-Anfrage-Limit ist erreicht. Bitte versuche es später erneut.")
            self._record(store, update_id, message_id, chat_id, question, "rate_limited", "rate_limit", started, received_at)
            return {"status": "rate_limited"}
        try:
            answer = self.answer(question)
            result = self._send(config, chat_id, answer)
            response_id = _message_id(result)
            self._last_sent_at = utc_now()
            self._record(store, update_id, message_id, chat_id, question, "sent", None, started, received_at, response_message_id=response_id, responded_at=utc_now())
            return {"status": "sent", "response_message_id": response_id}
        except Exception as exc:
            self._last_error = str(exc)
            self._record(store, update_id, message_id, chat_id, question, "failed", exc.__class__.__name__, started, received_at)
            self.messaging.create_message("telegram", "telegram", "warning", "Telegram-Antwort fehlgeschlagen", str(exc), {"chat_id": chat_id})
            raise

    def answer(self, question: str) -> str:
        context = self._context_snapshot()
        system = (
            "Du bist Roboter Steve im privaten Haushalt von Nawid. "
            "Antworte kurz, konkret und auf Deutsch. "
            "Du darfst ueber Status, Termine, Nachrichten, Garten, Energie und Home Assistant informieren. "
            "Fuehre ueber Telegram keine Aktionen an Geraeten aus und behaupte keine Aktion ausgefuehrt zu haben."
        )
        prompt = f"Kontext:\n{json.dumps(context, ensure_ascii=False, indent=2)[:12000]}\n\nNutzerfrage:\n{question}"
        try:
            response = create_llm_client().generate(prompt=prompt, system=system)
            text = str(response.text or "").strip()
            if text:
                return text[:4000]
        except Exception as exc:
            self._last_error = str(exc)
        return self._fallback_answer(question, context)

    def store(self, config: TelegramConfig | None = None) -> TelegramStore:
        if self._store is not None:
            return self._store
        return TelegramStore((config or self.config()).database_path)

    def client(self, config: TelegramConfig | None = None) -> TelegramApiClient:
        if self._client is not None:
            self._client.config = config or self.config()
            return self._client
        return TelegramApiClient(config or self.config())

    def test_send(self, text: str = "Roboter Steve Telegram ist verbunden.") -> dict[str, Any]:
        config = self.config()
        if not config.bot_token or not config.allowed_chat_ids:
            raise RuntimeError("Telegram Bot Token oder erlaubte Chat-ID fehlt.")
        result = self.client(config).send_message(config.allowed_chat_ids[0], text)
        return {"ok": True, "result": result}

    def bot_info(self) -> dict[str, Any]:
        config = self.config()
        if not config.bot_token:
            raise RuntimeError("Telegram Bot Token fehlt.")
        return self.client(config).get_me()

    def setup_info(self) -> dict[str, Any]:
        config = self.config()
        bot: dict[str, Any] = {}
        error = ""
        if config.bot_token:
            try:
                bot = self.client(config).get_me()
            except Exception as exc:
                error = str(exc)
        username = str(bot.get("username") or "").strip()
        bot_url = f"https://t.me/{username}" if username else ""
        return {
            "enabled": config.enabled,
            "configured": bool(config.bot_token and config.allowed_chat_ids),
            "bot_token_configured": bool(config.bot_token),
            "allowed_chat_ids": list(config.allowed_chat_ids),
            "allowed_chat_count": len(config.allowed_chat_ids),
            "auto_pair_first_chat": config.auto_pair_first_chat,
            "bot": bot,
            "bot_url": bot_url,
            "qr_payload": bot_url,
            "config_path": "agent-api/backend/agents/telegram/config.yaml",
            "env_keys": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
            "error": error,
        }

    def discover_chats(self) -> dict[str, Any]:
        config = self.config()
        if not config.bot_token:
            raise RuntimeError("Telegram Bot Token fehlt.")
        updates = self.client(config).get_updates(None)
        chats: dict[str, dict[str, Any]] = {}
        for update in updates:
            message = update.get("message") if isinstance(update.get("message"), dict) else {}
            chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
            chat_id = str(chat.get("id") or "").strip()
            if not chat_id:
                continue
            chats[chat_id] = {
                "chat_id": chat_id,
                "type": chat.get("type"),
                "title": chat.get("title"),
                "username": chat.get("username"),
                "first_name": chat.get("first_name"),
                "last_name": chat.get("last_name"),
                "latest_update_id": update.get("update_id"),
                "latest_message_id": message.get("message_id"),
                "authorized": chat_id in set(config.allowed_chat_ids),
            }
        return {"chats": list(chats.values())}

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            config = self.config()
            try:
                self.poll_once()
            except Exception as exc:
                self._last_error = str(exc)
            self._stop_event.wait(config.poll_interval_seconds)

    def _send(self, config: TelegramConfig, chat_id: str, text: str) -> dict[str, Any] | None:
        return self.client(config).send_message(chat_id, _telegram_text(text))

    def _record(
        self,
        store: TelegramStore,
        update_id: int,
        message_id: int | None,
        chat_id: str,
        question: str,
        status: str,
        error: str | None,
        started: float,
        received_at: str,
        response_message_id: int | None = None,
        responded_at: str | None = None,
    ) -> None:
        store.record(
            update_id=update_id,
            message_id=message_id,
            chat_id=chat_id,
            question=question,
            status=status,
            error=error,
            response_message_id=response_message_id,
            processing_ms=round((time.perf_counter() - started) * 1000),
            received_at=received_at,
            responded_at=responded_at,
        )

    def _context_snapshot(self) -> dict[str, Any]:
        context: dict[str, Any] = {"created_at": utc_now()}
        try:
            context["messages"] = MessagingService().get_messages(limit=10, unread_only=False)
        except Exception as exc:
            context["messages_error"] = str(exc)
        try:
            context["garden"] = GardenService().status()
        except Exception as exc:
            context["garden_error"] = str(exc)
        try:
            context["energy"] = HomeAssistantService().get_energy_overview()
        except Exception as exc:
            context["energy_error"] = str(exc)
        return context

    def _fallback_answer(self, question: str, context: dict[str, Any]) -> str:
        parts = ["Ich kann gerade keine KI-Antwort erzeugen, aber ich habe den Systemstatus gelesen."]
        garden = context.get("garden") if isinstance(context.get("garden"), dict) else {}
        if garden:
            summary = garden.get("summary") if isinstance(garden.get("summary"), dict) else {}
            parts.append(f"Garden: {summary.get('status') or garden.get('status') or 'unbekannt'}.")
        energy = context.get("energy") if isinstance(context.get("energy"), dict) else {}
        if energy:
            power = energy.get("power")
            parts.append(f"Energie: {power:g} W." if isinstance(power, (int, float)) else "Energie: keine aktuellen Leistungsdaten.")
        if "?" in question:
            parts.append("Für Details brauche ich einen funktionierenden LLM-Provider.")
        return " ".join(parts)[:4000]

    def _write_config(self, telegram_config: dict[str, Any]) -> None:
        path = AGENTS_DIR / self.agent_id / "config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump({"telegram": telegram_config}, allow_unicode=True, sort_keys=False), encoding="utf-8")


def config_public(config: TelegramConfig) -> dict[str, Any]:
    return {
        "enabled": config.enabled,
        "configured": bool(config.bot_token and config.allowed_chat_ids),
        "bot_token_configured": bool(config.bot_token),
        "allowed_chat_count": len(config.allowed_chat_ids),
        "auto_pair_first_chat": config.auto_pair_first_chat,
        "poll_interval_seconds": config.poll_interval_seconds,
        "timeout_seconds": config.timeout_seconds,
        "hourly_limit": config.hourly_limit,
        "daily_limit": config.daily_limit,
        "database_path": config.database_path,
    }


def _read_env_file() -> dict[str, str]:
    from backend.paths import ENV_PATH

    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _resolve_secret(value: Any, env_values: dict[str, str]) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for key in (text, text.upper(), text.replace("-", "_"), text.replace("-", "_").upper()):
        resolved = os.getenv(key) or env_values.get(key)
        if resolved:
            return resolved
    return "" if text.isupper() and "_" in text else text


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _allowed_chat_ids_without_bot_id(chat_ids: list[str], bot_token: str) -> list[str]:
    bot_id = _bot_id_from_token(bot_token)
    if not bot_id:
        return chat_ids
    return [chat_id for chat_id in chat_ids if chat_id != bot_id]


def _effective_allowed_chat_ids(config: TelegramConfig) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_allowed_chat_ids_without_bot_id(list(config.allowed_chat_ids), config.bot_token)))


def _bot_id_from_token(bot_token: str) -> str:
    prefix = str(bot_token or "").split(":", 1)[0].strip()
    return prefix if prefix.isdigit() else ""


def _int_value(value: Any, fallback: int, minimum: int) -> int:
    try:
        return max(int(value), minimum)
    except (TypeError, ValueError):
        return fallback


def _sanitize_question(value: str) -> str:
    text = " ".join(str(value or "").replace("\x00", "").split())
    return text[:1000]


def _telegram_text(value: str) -> str:
    return str(value or "").strip()[:4000] or "Ich habe keine Antwort erzeugen koennen."


def _message_id(result: dict[str, Any] | None) -> int | None:
    try:
        return int((result or {}).get("message_id") or 0) or None
    except (TypeError, ValueError):
        return None


def _question_hash(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()
