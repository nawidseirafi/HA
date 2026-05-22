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
            connection.commit()

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
        with self.connect() as connection:
            connection.execute("delete from invoices where id = ?", (invoice_id,))
            connection.commit()
        return {"deleted": True, "invoice": invoice}

    def reanalyze(self, invoice_id: int) -> dict[str, Any]:
        invoice = self.get(invoice_id)
        path = Path(invoice.get("stored_path") or invoice.get("archive_path") or invoice.get("source_path") or "")
        if not path.exists():
            raise HTTPException(status_code=404, detail="Document file not found")
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
        return {
            "status": "uploaded",
            "filename": safe_name,
            "stored_filename": stored_name,
            "path": str(destination),
        }

    def run_agent(self) -> dict[str, Any]:
        script = AI_AGENT_DIR / "agents" / "invoices.py"
        python = PROJECT_DIR / "venv" / "bin" / "python"
        command = [str(python if python.exists() else "python3"), str(script), "--once"]
        result = subprocess.run(command, cwd=AI_AGENT_DIR, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr.strip() or "InvoiceAgent failed")
        self._ensure_schema()
        return {"status": "completed", "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}

    def document_path(self, invoice_id: int) -> Path:
        invoice = self.get(invoice_id)
        raw_path = invoice.get("stored_path") or invoice.get("archive_path") or invoice.get("source_path")
        if not raw_path:
            raise HTTPException(status_code=404, detail="No document path stored")
        path = Path(raw_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Document file not found")
        return path

    def _reanalyze_with_ai(self, path: Path):
        if str(AI_AGENT_DIR) not in sys.path:
            sys.path.insert(0, str(AI_AGENT_DIR))
        from agents.invoices import load_raw_config  # type: ignore
        from core.invoice_ai_extractor import refine_metadata_with_ai  # type: ignore
        from core.invoice_extractor import extract_metadata  # type: ignore
        from llm import create_llm_client  # type: ignore

        raw_config = load_raw_config()
        llm_config = raw_config.get("llm", {})
        invoice_config = raw_config.get("invoice_agent", {})
        if not llm_config:
            raise RuntimeError("keine llm-Konfiguration vorhanden")
        metadata = extract_metadata(path, default_category=invoice_config.get("default_category", "Unsortiert"))
        llm_client = create_llm_client({"llm": llm_config})
        last_error = None
        for attempt in range(3):
            try:
                return refine_metadata_with_ai(
                    path=path,
                    metadata=metadata,
                    llm_client=llm_client,
                    default_category=invoice_config.get("default_category", "Unsortiert"),
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
