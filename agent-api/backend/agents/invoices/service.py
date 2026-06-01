import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import logging
import threading
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import yaml
from fastapi import HTTPException, UploadFile

from backend.config import load_agent_runtime_config
from backend.services.messaging import MessagingService
from backend.paths import API_DIR, PROJECT_DIR

logger = logging.getLogger(__name__)
DEFAULT_AGENT_TIMEOUT_SECONDS = 1800
DEFAULT_INVOICE_SCHEDULE = ["22:00:00"]


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
    "open_amount": "real",
    "paid_amount": "real",
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
    return load_agent_runtime_config("invoices")


def resolve_path(value: Any, default_base: Path = API_DIR) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (default_base / path).resolve()


def configured_paths() -> dict[str, Path]:
    config = load_config()
    invoice_config = config.get("invoices", {})
    data_dir = API_DIR / "data" / "invoices"
    return {
        "database": resolve_path(invoice_config.get("database_path", data_dir / "invoices.db")),
        "inbox": resolve_path(invoice_config.get("inbox_dir", invoice_config.get("upload_dir", data_dir / "inbox"))),
        "archive": resolve_path(invoice_config.get("archive_dir", data_dir / "archive")),
        "review": resolve_path(invoice_config.get("review_dir", data_dir / "review")),
        "exports": resolve_path(invoice_config.get("export_dir", data_dir / "exports")),
        "archive_cleanup_backup": resolve_path(invoice_config.get("archive_cleanup", {}).get("backup_dir", data_dir / "archive_cleanup_backup")),
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
        self.run_lock = threading.Lock()
        self.scheduler_stop = threading.Event()
        self.scheduler_thread: Optional[threading.Thread] = None
        self.paths = configured_paths()
        self.database_path = self.paths["database"]
        self.inbox_dir = self.paths["inbox"]
        self.archive_dir = self.paths["archive"]
        self.review_dir = self.paths["review"]
        self.export_dir = self.paths["exports"]
        self.archive_cleanup_backup_dir = self.paths["archive_cleanup_backup"]
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                create table if not exists invoices (
                    id integer primary key autoincrement,
                    file_hash text unique,
                    source_path text,
                    archive_path text,
                    is_invoice integer not null default 1,
                    confidence real not null default 0,
                    vendor text not null default '',
                    invoice_date text not null,
                    amount real,
                    currency text not null default 'EUR',
                    invoice_number text,
                    category text not null default 'Unsortiert',
                    status text not null default 'new',
                    reason text,
                    updated_at text not null
                )
                """
            )
            existing = {row["name"] for row in connection.execute("pragma table_info(invoices)").fetchall()}
            for column, definition in EXTRA_COLUMNS.items():
                if column not in existing:
                    connection.execute(f"alter table invoices add column {column} {definition}")
            connection.execute(
                """
                update invoices
                set
                    source = coalesce(source, 'agent'),
                    original_filename = coalesce(original_filename, nullif(source_path, '')),
                    stored_path = coalesce(stored_path, archive_path, source_path),
                    document_type = coalesce(document_type, case when is_invoice = 1 then 'invoice' else 'document' end),
                    transaction_type = coalesce(transaction_type, 'expense'),
                    year = coalesce(year, cast(substr(invoice_date, 1, 4) as integer)),
                    month = coalesce(month, cast(substr(invoice_date, 6, 2) as integer)),
                    gross_amount = coalesce(gross_amount, amount),
                    open_amount = case when abs(coalesce(open_amount, -1) - coalesce(gross_amount, amount, -2)) < 0.005 and coalesce(paid_amount, 0) = 0 then null else open_amount end,
                    paid_amount = case when abs(coalesce(open_amount, -1) - coalesce(gross_amount, amount, -2)) < 0.005 and coalesce(paid_amount, 0) = 0 then null else paid_amount end,
                    review_status = coalesce(
                        review_status,
                        case
                            when status = 'archived' then 'reviewed'
                            when status = 'review' then 'needs_review'
                            else status
                        end
                    ),
                    ai_confidence = coalesce(ai_confidence, confidence),
                    created_at = coalesce(created_at, updated_at)
                """
            )
            connection.execute(
                """
                create table if not exists invoice_agent_settings (
                    id integer primary key check (id = 1),
                    enabled integer not null default 1,
                    schedule_json text not null default '["08:00:00","18:00:00"]',
                    last_status text not null default 'idle',
                    last_successful_run text,
                    last_started_at text,
                    last_finished_at text,
                    last_error text,
                    last_output text,
                    updated_at text not null
                )
                """
            )
            connection.execute(
                """
                insert or ignore into invoice_agent_settings
                    (id, enabled, schedule_json, updated_at)
                values (?, ?, ?, ?)
                """,
                (
                    1,
                    1 if self._invoice_api_config().get("enabled", True) else 0,
                    yaml.safe_dump(self._configured_schedule(), default_flow_style=True).strip(),
                    utc_now(),
                ),
            )
            row = connection.execute("select schedule_json from invoice_agent_settings where id = 1").fetchone()
            if row is not None:
                try:
                    current_schedule = yaml.safe_load(row["schedule_json"] or "[]") or []
                except yaml.YAMLError:
                    current_schedule = []
                if isinstance(current_schedule, list):
                    normalized = [self._normalize_time_string(value) for value in current_schedule if str(value).strip()]
                    if normalized == ["08:00:00", "18:00:00"]:
                        connection.execute(
                            """
                            update invoice_agent_settings
                            set schedule_json = ?, updated_at = ?
                            where id = 1
                            """,
                            (yaml.safe_dump(DEFAULT_INVOICE_SCHEDULE, default_flow_style=True).strip(), utc_now()),
                        )
            connection.commit()

    def status(self) -> dict[str, Any]:
        settings = self._agent_settings()
        running = self.run_lock.locked()
        next_scheduled = self._next_scheduled(settings["schedule"]) if settings["enabled"] else None
        current_status = self._control_status(settings, running)
        return {
            "enabled": settings["enabled"],
            "is_running": running,
            "status": current_status,
            "current_status": current_status,
            "last_status": settings["last_status"],
            "last_successful_run": settings["last_successful_run"],
            "last_started_at": settings["last_started_at"],
            "last_finished_at": settings["last_finished_at"],
            "last_error": settings["last_error"],
            "last_output": settings["last_output"],
            "schedule": settings["schedule"],
            "next_scheduled_run": next_scheduled,
            "updated_at": settings["updated_at"],
        }

    def _control_status(self, settings: dict[str, Any], running: bool) -> str:
        if running:
            return "running"
        if not settings.get("enabled"):
            return "disabled"
        raw = str(settings.get("last_status") or "").lower()
        if settings.get("last_error") or "error" in raw or "failed" in raw:
            return "error"
        return "active"

    def enable(self) -> dict[str, Any]:
        self._write_agent_settings(enabled=True, last_status="enabled", last_error=None)
        logger.info("InvoiceAgent aktiviert.")
        return self.status()

    def disable(self) -> dict[str, Any]:
        self._write_agent_settings(enabled=False, last_status="disabled")
        logger.info("InvoiceAgent deaktiviert.")
        return self.status()

    def toggle(self) -> dict[str, Any]:
        return self.disable() if self._agent_settings()["enabled"] else self.enable()

    def update_agent_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if "enabled" in payload:
            updates["enabled"] = bool(payload["enabled"])
        if "schedule" in payload:
            schedule = payload["schedule"]
            if not isinstance(schedule, list):
                raise HTTPException(status_code=422, detail="schedule muss eine Liste sein.")
            updates["schedule"] = [self._normalize_time_string(value) for value in schedule if str(value).strip()]
            if not updates["schedule"]:
                raise HTTPException(status_code=422, detail="schedule darf nicht leer sein.")
        if updates:
            updates["last_status"] = "configured"
            updates["last_error"] = None
            self._write_agent_settings(**updates)
        return self.status()

    def start_scheduler(self) -> None:
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            return
        self.scheduler_stop.clear()
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        logger.info("InvoiceAgent Scheduler gestartet.")

    def stop_scheduler(self) -> None:
        self.scheduler_stop.set()

    def _scheduler_loop(self) -> None:
        last_run: dict[str, str] = {}
        while not self.scheduler_stop.is_set():
            now = datetime.now().astimezone()
            settings = self._agent_settings()
            if settings["enabled"]:
                for run_time in self._parse_schedule(settings["schedule"]):
                    run_key = f"{run_time.isoformat()}:{now.date().isoformat()}"
                    scheduled_at = datetime.combine(now.date(), run_time, tzinfo=now.tzinfo)
                    seconds_from_schedule = (now - scheduled_at).total_seconds()
                    if 0 <= seconds_from_schedule < 2 and run_key not in last_run:
                        last_run[run_key] = utc_now()
                        threading.Thread(target=self._run_scheduled_agent, daemon=True).start()
            self.scheduler_stop.wait(1)

    def _run_scheduled_agent(self) -> None:
        try:
            self.run_agent()
        except HTTPException as exc:
            logger.warning("Geplanter InvoiceAgent-Lauf fehlgeschlagen: %s", exc.detail)
        except Exception:
            logger.exception("Geplanter InvoiceAgent-Lauf fehlgeschlagen.")

    def _invoice_api_config(self) -> dict[str, Any]:
        return load_config().get("invoices", {}) or {}

    def _configured_schedule(self) -> list[str]:
        configured = self._invoice_api_config().get("schedule", DEFAULT_INVOICE_SCHEDULE)
        if not isinstance(configured, list):
            return DEFAULT_INVOICE_SCHEDULE
        try:
            return [self._normalize_time_string(value) for value in configured if str(value).strip()] or DEFAULT_INVOICE_SCHEDULE
        except HTTPException:
            return DEFAULT_INVOICE_SCHEDULE

    def _agent_settings(self) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("select * from invoice_agent_settings where id = 1").fetchone()
        if row is None:
            self._ensure_schema()
            return self._agent_settings()
        data = dict(row)
        try:
            schedule = yaml.safe_load(data.get("schedule_json") or "") or []
        except yaml.YAMLError:
            schedule = []
        if not isinstance(schedule, list):
            schedule = []
        return {
            "enabled": bool(data.get("enabled")),
            "schedule": [self._normalize_time_string(value) for value in schedule if str(value).strip()] or DEFAULT_INVOICE_SCHEDULE,
            "last_status": data.get("last_status") or "idle",
            "last_successful_run": data.get("last_successful_run"),
            "last_started_at": data.get("last_started_at"),
            "last_finished_at": data.get("last_finished_at"),
            "last_error": data.get("last_error"),
            "last_output": data.get("last_output") or "",
            "updated_at": data.get("updated_at"),
        }

    def _write_agent_settings(self, **values: Any) -> None:
        if not values:
            return
        updates = dict(values)
        if "enabled" in updates:
            updates["enabled"] = 1 if updates["enabled"] else 0
        if "schedule" in updates:
            updates["schedule_json"] = yaml.safe_dump(updates.pop("schedule"), default_flow_style=True).strip()
        allowed = {
            "enabled",
            "schedule_json",
            "last_status",
            "last_successful_run",
            "last_started_at",
            "last_finished_at",
            "last_error",
            "last_output",
        }
        updates = {key: value for key, value in updates.items() if key in allowed}
        if not updates:
            return
        updates["updated_at"] = utc_now()
        columns = ", ".join(f"{key} = ?" for key in updates)
        with self.connect() as connection:
            connection.execute(f"update invoice_agent_settings set {columns} where id = 1", list(updates.values()))
            connection.commit()

    def _parse_schedule(self, schedule: list[str]) -> list[datetime_time]:
        return sorted(self._parse_time(value) for value in schedule)

    def _parse_time(self, value: Any) -> datetime_time:
        normalized = self._normalize_time_string(value)
        return datetime_time.fromisoformat(normalized)

    @staticmethod
    def _normalize_time_string(value: Any) -> str:
        text = str(value).strip()
        if re.fullmatch(r"\d{1,2}:\d{2}", text):
            text = f"{text}:00"
        if not re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", text):
            raise HTTPException(status_code=422, detail=f"Ungueltige Uhrzeit: {value}")
        hour, minute, second = (int(part) for part in text.split(":"))
        text = f"{hour:02d}:{minute:02d}:{second:02d}"
        parsed = datetime_time.fromisoformat(text)
        return parsed.isoformat()

    def _next_scheduled(self, schedule: list[str]) -> Optional[str]:
        now = datetime.now().astimezone()
        run_times = self._parse_schedule(schedule)
        for day_offset in range(2):
            target_date = now.date() + timedelta(days=day_offset)
            for run_time in run_times:
                candidate = datetime.combine(target_date, run_time, tzinfo=now.tzinfo)
                if candidate > now:
                    return candidate.isoformat(timespec="seconds")
        return None

    def summary(self) -> dict[str, Any]:
        today = date.today()
        with self.connect() as connection:
            total = self._scalar(connection, "select count(*) from invoices")
            month_total = self._scalar(
                connection,
                """
                select coalesce(sum(coalesce(gross_amount, amount, 0)), 0)
                from invoices
                where year = ? and month = ? and coalesce(transaction_type, 'expense') = 'expense'
                """,
                (today.year, today.month),
            )
            year_total = self._scalar(
                connection,
                """
                select coalesce(sum(coalesce(gross_amount, amount, 0)), 0)
                from invoices
                where year = ? and coalesce(transaction_type, 'expense') = 'expense'
                """,
                (today.year,),
            )
            needs_review = self._scalar(
                connection,
                "select count(*) from invoices where coalesce(review_status, status) in ('new', 'needs_review', 'review')",
            )
            errors = self._scalar(
                connection,
                "select count(*) from invoices where coalesce(review_status, status) = 'error'",
            )
            latest = self._fetch_all(
                connection,
                "select * from invoices order by coalesce(created_at, updated_at) desc limit 8",
            )
        return {
            "total_invoices": total,
            "current_month_total": month_total,
            "current_year_total": year_total,
            "needs_review_count": needs_review,
            "ai_error_count": errors,
            "latest_uploads": [self._row_to_invoice(row) for row in latest],
        }

    def years(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                select year,
                       coalesce(sum(case when coalesce(transaction_type, 'expense') = 'income' then coalesce(gross_amount, amount, 0) else 0 end), 0) as income_total,
                       coalesce(sum(case when coalesce(transaction_type, 'expense') = 'expense' then coalesce(gross_amount, amount, 0) else 0 end), 0) as expense_total,
                       coalesce(sum(case when coalesce(transaction_type, 'expense') = 'income' then coalesce(gross_amount, amount, 0) else -coalesce(gross_amount, amount, 0) end), 0) as total,
                       count(*) as invoice_count,
                       sum(case when coalesce(review_status, status) in ('new', 'needs_review', 'review') then 1 else 0 end) as needs_review_count
                from invoices
                where year is not null
                group by year
                order by year desc
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def year(self, year: int) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                select month,
                       coalesce(sum(case when coalesce(transaction_type, 'expense') = 'income' then coalesce(gross_amount, amount, 0) else 0 end), 0) as income_total,
                       coalesce(sum(case when coalesce(transaction_type, 'expense') = 'expense' then coalesce(gross_amount, amount, 0) else 0 end), 0) as expense_total,
                       count(*) as invoice_count,
                       sum(case when coalesce(review_status, status) in ('new', 'needs_review', 'review') then 1 else 0 end) as needs_review_count
                from invoices
                where year = ?
                group by month
                """,
                (year,),
            ).fetchall()
        by_month = {row["month"]: dict(row) for row in rows}
        months = [
            {
                "year": year,
                "month": month,
                "income_total": by_month.get(month, {}).get("income_total", 0),
                "expense_total": by_month.get(month, {}).get("expense_total", 0),
                "invoice_count": by_month.get(month, {}).get("invoice_count", 0),
                "needs_review_count": by_month.get(month, {}).get("needs_review_count", 0),
            }
            for month in range(1, 13)
        ]
        return {"year": year, "months": months}

    def month(self, year: int, month: int, filters: dict[str, Any]) -> dict[str, Any]:
        where = ["year = ?", "month = ?"]
        params: list[Any] = [year, month]
        for key, column in (("category", "category"), ("status", "coalesce(review_status, status)"), ("vendor", "vendor")):
            value = filters.get(key)
            if value:
                where.append(f"lower({column}) like ?")
                params.append(f"%{str(value).lower()}%")
        if filters.get("amount_min") is not None:
            where.append("coalesce(gross_amount, amount, 0) >= ?")
            params.append(filters["amount_min"])
        if filters.get("amount_max") is not None:
            where.append("coalesce(gross_amount, amount, 0) <= ?")
            params.append(filters["amount_max"])
        if filters.get("search"):
            where.append("(lower(vendor) like ? or lower(category) like ? or lower(coalesce(invoice_number, '')) like ?)")
            needle = f"%{str(filters['search']).lower()}%"
            params.extend([needle, needle, needle])

        with self.connect() as connection:
            rows = connection.execute(
                f"select * from invoices where {' and '.join(where)} order by invoice_date desc, vendor",
                params,
            ).fetchall()
        return {"year": year, "month": month, "invoices": [self._row_to_invoice(row) for row in rows]}

    def get(self, invoice_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("select * from invoices where id = ?", (invoice_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Invoice not found")
        return self._row_to_invoice(row)

    def update(self, invoice_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "vendor",
            "invoice_number",
            "invoice_date",
            "category",
            "payment_method",
            "transaction_type",
            "net_amount",
            "tax_amount",
            "gross_amount",
            "open_amount",
            "paid_amount",
            "currency",
            "is_business",
            "is_tax_relevant",
            "review_status",
            "notes",
            "document_type",
        }
        updates = {key: payload[key] for key in allowed if key in payload}
        if "invoice_date" in updates and updates["invoice_date"]:
            parsed = date.fromisoformat(str(updates["invoice_date"])[:10])
            updates["invoice_date"] = parsed.isoformat()
            updates["year"] = parsed.year
            updates["month"] = parsed.month
        if "gross_amount" in updates:
            updates["amount"] = updates["gross_amount"]
        if "review_status" in updates:
            updates["status"] = self._status_from_review(updates["review_status"])
        if updates.get("transaction_type") not in (None, "income", "expense"):
            raise HTTPException(status_code=422, detail="transaction_type must be income or expense")
        updates["updated_at"] = utc_now()
        if not updates:
            return self.get(invoice_id)
        columns = ", ".join(f"{key} = ?" for key in updates)
        with self.connect() as connection:
            connection.execute(f"update invoices set {columns} where id = ?", [*updates.values(), invoice_id])
            connection.commit()
        return self.get(invoice_id)

    def mark_reviewed(self, invoice_id: int) -> dict[str, Any]:
        return self.update(invoice_id, {"review_status": "reviewed"})

    def delete(self, invoice_id: int) -> dict[str, Any]:
        invoice = self.get(invoice_id)
        deleted_files = self._delete_invoice_files(invoice, invoice_id)
        with self.connect() as connection:
            connection.execute("delete from invoices where id = ?", (invoice_id,))
            connection.commit()
        return {"deleted": True, "deleted_files": [str(path) for path in deleted_files], "invoice": invoice}

    def reanalyze(self, invoice_id: int) -> dict[str, Any]:
        invoice = self.get(invoice_id)
        path = self._resolve_document_path(invoice.get("stored_path") or invoice.get("archive_path") or invoice.get("source_path"))
        try:
            metadata = self._reanalyze_with_ai(path)
        except Exception as exc:
            self.update(invoice_id, {"review_status": "error", "notes": f"KI-Reanalyse fehlgeschlagen: {exc}"})
            raise HTTPException(status_code=500, detail=f"KI-Reanalyse fehlgeschlagen: {exc}") from exc

        payload = {
            "vendor": metadata.vendor,
            "invoice_number": metadata.invoice_number,
            "invoice_date": metadata.invoice_date.isoformat(),
            "category": metadata.category,
            "net_amount": metadata.net_amount,
            "tax_amount": metadata.tax_amount,
            "gross_amount": metadata.gross_amount if metadata.gross_amount is not None else metadata.amount,
            "open_amount": metadata.open_amount,
            "paid_amount": metadata.paid_amount,
            "currency": metadata.currency,
            "review_status": "needs_review",
            "document_type": metadata.document_type,
            "transaction_type": metadata.transaction_type,
            "is_business": metadata.is_business,
            "is_tax_relevant": metadata.is_tax_relevant,
        }
        self.update(invoice_id, payload)
        with self.connect() as connection:
            connection.execute(
                "update invoices set reason = ?, ai_raw_json = ?, ai_confidence = ? where id = ?",
                (metadata.reason, metadata.ai_raw_json or metadata.reason, metadata.confidence, invoice_id),
            )
            connection.commit()
        updated = self.get(invoice_id)
        return {
            "status": "reanalyzed",
            "message": "Beleg wurde erneut mit KI analysiert und zur Pruefung markiert.",
            "invoice": updated,
        }

    def upload(self, file: UploadFile) -> dict[str, Any]:
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        safe_name = secure_filename(file.filename or "upload")
        stored_name = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex}-{safe_name}"
        destination = self.inbox_dir / stored_name
        with destination.open("wb") as output_file:
            shutil.copyfileobj(file.file, output_file)
        result = {
            "status": "uploaded",
            "filename": safe_name,
            "stored_filename": stored_name,
            "path": str(destination),
        }
        try:
            MessagingService().create_message(
                source="invoice",
                category="invoice",
                severity="info",
                title="Rechnung verarbeitet",
                message=f"Beleg {safe_name} wurde hochgeladen.",
                payload={"filename": safe_name, "stored_filename": stored_name},
            )
        except Exception:
            pass
        return result

    def run_agent(self) -> dict[str, Any]:
        if not self.run_lock.acquire(blocking=False):
            logger.info("InvoiceAgent uebersprungen, weil bereits ein Lauf aktiv ist.")
            return {**self.status(), "status": "running", "message": "InvoiceAgent laeuft bereits."}
        python = PROJECT_DIR / "venv" / "bin" / "python"
        command = [str(python if python.exists() else sys.executable), "-m", "backend.agents.invoices.invoices", "--once"]
        invoice_config = load_config().get("invoices", {})
        timeout_seconds = int(invoice_config.get("run_timeout_seconds", DEFAULT_AGENT_TIMEOUT_SECONDS))
        logger.info("InvoiceAgent startet: command=%s cwd=%s timeout=%s", command, API_DIR, timeout_seconds)
        started_at = utc_now()
        self._write_agent_settings(last_status="running", last_started_at=started_at, last_error=None)
        try:
            env = os.environ.copy() | {"PYTHONPATH": str(API_DIR)}
            result = subprocess.run(command, cwd=API_DIR, env=env, capture_output=True, text=True, timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            logger.warning("InvoiceAgent Timeout nach %s Sekunden.", timeout_seconds)
            self._write_agent_settings(last_status="error", last_finished_at=utc_now(), last_error=f"Timeout nach {timeout_seconds} Sekunden.")
            raise HTTPException(status_code=504, detail=f"InvoiceAgent Timeout nach {timeout_seconds} Sekunden.") from exc
        except OSError as exc:
            logger.exception("InvoiceAgent konnte nicht gestartet werden.")
            self._write_agent_settings(last_status="error", last_finished_at=utc_now(), last_error=str(exc))
            raise HTTPException(status_code=500, detail=f"InvoiceAgent konnte nicht gestartet werden: {exc}") from exc
        finally:
            if "result" not in locals():
                self.run_lock.release()
        try:
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            output = "\n".join(part for part in (stdout, stderr) if part)
            if stdout:
                logger.info("InvoiceAgent stdout: %s", stdout[-3000:])
            if stderr:
                logger.warning("InvoiceAgent stderr: %s", stderr[-3000:])
            if result.returncode != 0:
                detail = (stderr or stdout or "InvoiceAgent failed")[-3000:]
                logger.error("InvoiceAgent fehlgeschlagen: returncode=%s detail=%s", result.returncode, detail)
                self._write_agent_settings(last_status="error", last_finished_at=utc_now(), last_error=detail, last_output=output[-8000:])
                raise HTTPException(status_code=500, detail=detail)
            self._ensure_schema()
            self._write_agent_settings(
                last_status="ok",
                last_successful_run=utc_now(),
                last_finished_at=utc_now(),
                last_error=None,
                last_output=output[-8000:],
            )
            return {
                "status": "completed",
                "command": " ".join(command),
                "cwd": str(API_DIR),
                "stdout": stdout,
                "stderr": stderr,
            }
        finally:
            self.run_lock.release()

    def cleanup_archive(self, apply: bool = False) -> dict[str, Any]:
        referenced = self._referenced_archive_paths()
        archive_files = self._archive_files()
        unreferenced = sorted(archive_files - referenced)
        missing = sorted(referenced - archive_files)

        backup_dir = None
        moved = []
        if apply and unreferenced:
            backup_dir = self.archive_cleanup_backup_dir / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            for source in unreferenced:
                relative = source.relative_to(self.archive_dir)
                target = backup_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))
                moved.append(target)
            self._remove_empty_dirs(self.archive_dir)

        return {
            "applied": apply,
            "archive_files": len(archive_files),
            "db_references": len(referenced),
            "unreferenced": len(unreferenced),
            "missing": len(missing),
            "moved": len(moved),
            "backup_dir": str(backup_dir) if backup_dir else None,
            "unreferenced_examples": [str(path) for path in unreferenced[:20]],
            "missing_examples": [str(path) for path in missing[:20]],
        }

    def document_path(self, invoice_id: int) -> Path:
        invoice = self.get(invoice_id)
        raw_path = invoice.get("stored_path") or invoice.get("archive_path") or invoice.get("source_path")
        return self._resolve_document_path(raw_path)

    def _resolve_document_path(self, raw_path: Any) -> Path:
        if not raw_path:
            raise HTTPException(status_code=404, detail="No document path stored")

        path = Path(str(raw_path)).expanduser()
        candidates = [path]

        if not path.is_absolute():
            candidates.append((API_DIR / path).resolve())
            candidates.append((API_DIR / path).resolve())

        parts = path.parts
        for index in range(len(parts) - 1):
            if parts[index] == "data" and parts[index + 1] == "invoices":
                candidates.append((API_DIR / Path(*parts[index:])).resolve())
                break

        if path.name:
            for root in (self.archive_dir, self.inbox_dir, self.review_dir):
                if root.exists():
                    candidates.extend(root.rglob(path.name))

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate

        raise HTTPException(status_code=404, detail=f"Document file not found: {path.name or raw_path}")

    def _referenced_archive_paths(self) -> set[Path]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                select archive_path
                from invoices
                where status = 'archived'
                  and archive_path is not null and archive_path != ''
                """
            ).fetchall()
        referenced = set()
        for row in rows:
            path = Path(str(row["archive_path"])).expanduser()
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if self._is_inside_any(resolved, [self.archive_dir]):
                referenced.add(resolved)
        return referenced

    def _archive_files(self) -> set[Path]:
        if not self.archive_dir.exists():
            return set()
        return {
            path.resolve()
            for path in self.archive_dir.rglob("*")
            if path.is_file() and path.name != "index.xlsx"
        }

    @staticmethod
    def _remove_empty_dirs(root: Path) -> None:
        for path in sorted((item for item in root.rglob("*") if item.is_dir()), reverse=True):
            try:
                path.rmdir()
            except OSError:
                pass

    def _delete_invoice_files(self, invoice: dict[str, Any], invoice_id: int) -> list[Path]:
        paths = []
        for key in ("stored_path", "archive_path", "source_path"):
            raw_path = invoice.get(key)
            if raw_path:
                paths.append(Path(str(raw_path)).expanduser())

        deleted = []
        for path in self._existing_managed_paths(paths):
            if self._is_path_referenced_by_other_invoice(path, invoice_id):
                continue
            try:
                path.unlink()
                deleted.append(path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise HTTPException(status_code=500, detail=f"Datei konnte nicht geloescht werden: {path.name}") from exc
        return deleted

    def _existing_managed_paths(self, paths: list[Path]) -> list[Path]:
        managed_roots = [self.archive_dir, self.inbox_dir, self.review_dir]
        candidates = []
        for path in paths:
            candidates.append(path)
            if not path.is_absolute():
                candidates.append((API_DIR / path).resolve())

        resolved_paths = []
        seen = set()
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved in seen or not resolved.exists() or not resolved.is_file():
                continue
            if not self._is_inside_any(resolved, managed_roots):
                continue
            seen.add(resolved)
            resolved_paths.append(resolved)
        return resolved_paths

    def _is_path_referenced_by_other_invoice(self, path: Path, invoice_id: int) -> bool:
        with self.connect() as connection:
            rows = connection.execute(
                """
                select stored_path, archive_path, source_path
                from invoices
                where id != ?
                """,
                (invoice_id,),
            ).fetchall()
        try:
            resolved = path.resolve()
        except OSError:
            return False
        for row in rows:
            for key in ("stored_path", "archive_path", "source_path"):
                raw_path = row[key]
                if not raw_path:
                    continue
                try:
                    if Path(str(raw_path)).expanduser().resolve() == resolved:
                        return True
                except OSError:
                    continue
        return False

    @staticmethod
    def _is_inside_any(path: Path, roots: list[Path]) -> bool:
        for root in roots:
            try:
                path.relative_to(root.resolve())
                return True
            except (OSError, ValueError):
                continue
        return False

    def _reanalyze_with_ai(self, path: Path):
        from backend.agents.invoices.invoices import load_raw_config
        from backend.agents.invoices.ai_extractor import refine_metadata_with_ai
        from backend.agents.invoices.categories import apply_category_rules
        from backend.agents.invoices.extractor import extract_metadata
        from backend.agents.invoices.tax_export import DEFAULT_CATEGORY_RULES
        from backend.services.llm.factory import create_llm_client

        raw_config = load_raw_config()
        llm_config = raw_config.get("llm", {})
        invoice_config = raw_config.get("invoices", {})
        tax_config = invoice_config.get("tax_export", {})
        category_rules = dict(DEFAULT_CATEGORY_RULES)
        category_rules.update(tax_config.get("categories", {}))
        if not llm_config:
            raise RuntimeError("keine llm-Konfiguration vorhanden")
        metadata = extract_metadata(path, default_category=invoice_config.get("default_category", "Unsortiert"))
        metadata = apply_category_rules(
            metadata,
            category_rules,
            invoice_config.get("default_category", "Unsortiert"),
        )
        llm_client = create_llm_client()
        last_error = None
        for attempt in range(3):
            try:
                metadata = refine_metadata_with_ai(
                    path=path,
                    metadata=metadata,
                    llm_client=llm_client,
                    default_category=invoice_config.get("default_category", "Unsortiert"),
                )
                return apply_category_rules(
                    metadata,
                    category_rules,
                    invoice_config.get("default_category", "Unsortiert"),
                )
            except Exception as exc:
                last_error = exc
                message = str(exc).lower()
                if "429" not in message and "too many" not in message and "rate" not in message:
                    raise
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
        raise last_error

    def rows_for_period(self, year: int, month: Optional[int] = None) -> list[dict[str, Any]]:
        with self.connect() as connection:
            if month is None:
                rows = connection.execute(
                    "select * from invoices where year = ? order by invoice_date, vendor",
                    (year,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "select * from invoices where year = ? and month = ? order by invoice_date, vendor",
                    (year, month),
                ).fetchall()
        return [self._row_to_invoice(row) for row in rows]

    @staticmethod
    def _scalar(connection: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> Any:
        return connection.execute(query, params).fetchone()[0]

    @staticmethod
    def _fetch_all(connection: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        return connection.execute(query, params).fetchall()

    @staticmethod
    def _status_from_review(review_status: str) -> str:
        if review_status == "reviewed":
            return "archived"
        if review_status == "needs_review":
            return "review"
        return review_status

    @staticmethod
    def _row_to_invoice(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["stored_path"] = data.get("stored_path") or data.get("archive_path") or data.get("source_path")
        data["original_filename"] = Path(data.get("original_filename") or data.get("source_path") or "").name
        data["gross_amount"] = data.get("gross_amount") if data.get("gross_amount") is not None else data.get("amount")
        data["ai_confidence"] = data.get("ai_confidence") if data.get("ai_confidence") is not None else data.get("confidence")
        data["review_status"] = data.get("review_status") or data.get("status")
        data["transaction_type"] = data.get("transaction_type") or "expense"
        data["year"] = data.get("year") or int(str(data["invoice_date"])[:4])
        data["month"] = data.get("month") or int(str(data["invoice_date"])[5:7])
        data["is_business"] = bool(data.get("is_business", 1))
        data["is_tax_relevant"] = bool(data.get("is_tax_relevant", 1))
        return data
