import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import yaml
from fastapi import HTTPException, UploadFile

BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BASE_DIR.parent
CONFIG_PATH = BASE_DIR / "config.yaml"
AI_AGENT_DIR = PROJECT_DIR / "ai-agent"
DEFAULT_DB_PATH = AI_AGENT_DIR / "data" / "invoices" / "invoices.db"
DEFAULT_INBOX_DIR = AI_AGENT_DIR / "data" / "invoices" / "inbox"
DEFAULT_ARCHIVE_DIR = AI_AGENT_DIR / "data" / "invoices" / "archive"
DEFAULT_EXPORT_DIR = AI_AGENT_DIR / "data" / "invoices" / "exports"

EXTRA_COLUMNS: dict[str, str] = {
    "source": "text",
    "original_filename": "text",
    "stored_path": "text",
    "document_type": "text",
    "transaction_type": "text not null default 'expense'",
    "year": "integer",
    "month": "integer",
    "payment_method": "text",
    "net_amount": "real",
    "tax_amount": "real",
    "gross_amount": "real",
    "is_business": "integer not null default 1",
    "is_tax_relevant": "integer not null default 1",
    "review_status": "text",
    "ai_confidence": "real",
    "ai_raw_json": "text",
    "notes": "text",
    "created_at": "text",
}

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file) or {}

def resolve_path(value: Any, default_base: Path = BASE_DIR) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (default_base / path).resolve()

def configured_paths() -> dict[str, Path]:
    config = load_config()
    storage = config.get("storage", {})
    invoice_config = config.get("agents", {}).get("invoices", {})
    inbox_dir = resolve_path(invoice_config.get("upload_dir", storage.get("uploads_dir", DEFAULT_INBOX_DIR)))
    return {
        "database": DEFAULT_DB_PATH,
        "inbox": inbox_dir,
        "archive": DEFAULT_ARCHIVE_DIR,
        "exports": DEFAULT_EXPORT_DIR,
    }

def secure_filename(filename: str) -> str:
    path_name = Path(filename).name
    stem = Path(path_name).stem.strip().lower()
    suffix = Path(path_name).suffix.lower()
    safe_stem = re.sub(r"[^a-z0-9._-]+", "_", stem)
    safe_stem = safe_stem.strip("._-") or "upload"
    safe_suffix = suffix if re.fullmatch(r"\.[a-z0-9]{1,12}", suffix) else ""
    return f"{safe_stem}{safe_suffix}"

class InvoiceService:
    def __init__(self):
        self.paths = configured_paths()
        self.database_path = self.paths["database"]
        self.inbox_dir = self.paths["inbox"]
        self.archive_dir = self.paths["archive"]
        self.export_dir = self.paths["exports"]
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        # ...existing code...
        pass
