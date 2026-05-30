import sqlite3
import zipfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape

from invoices.archiver import month_dir_for
from invoices.extractor import InvoiceMetadata


HEADERS = (
    "Datum",
    "Anbieter",
    "Netto",
    "MwSt",
    "Brutto",
    "Offen",
    "Bezahlt",
    "Waehrung",
    "Rechnungsnummer",
    "Dokumenttyp",
    "Art",
    "Kategorie",
    "Quelle",
    "Archivpfad",
    "Hash",
    "Konfidenz",
    "Status",
)


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


class InvoiceCatalog:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def close(self):
        self.connection.close()

    def has_hash(self, file_hash: str) -> bool:
        row = self.connection.execute(
            "select 1 from invoices where file_hash = ? limit 1",
            (file_hash,),
        ).fetchone()
        return row is not None

    def has_metadata_duplicate(self, metadata: InvoiceMetadata) -> bool:
        if metadata.invoice_number:
            row = self.connection.execute(
                """
                select 1 from invoices
                where status = 'archived'
                  and lower(vendor) = lower(?)
                  and lower(invoice_number) = lower(?)
                limit 1
                """,
                (metadata.vendor, metadata.invoice_number),
            ).fetchone()
            if row is not None:
                return True

        if metadata.amount is None:
            return False

        row = self.connection.execute(
            """
            select 1 from invoices
            where status = 'archived'
              and lower(vendor) = lower(?)
              and invoice_date = ?
              and abs(amount - ?) < 0.005
            limit 1
            """,
            (metadata.vendor, metadata.invoice_date.isoformat(), metadata.amount),
        ).fetchone()
        return row is not None

    def has_email_message(self, message_key: str) -> bool:
        row = self.connection.execute(
            "select 1 from email_messages where message_key = ? limit 1",
            (message_key,),
        ).fetchone()
        return row is not None

    def record_email_message(self, message_key: str) -> None:
        self.connection.execute(
            """
            insert or ignore into email_messages (message_key, processed_at)
            values (?, ?)
            """,
            (message_key, datetime.utcnow().isoformat(timespec="seconds")),
        )
        self.connection.commit()

    def upsert(self, metadata: InvoiceMetadata, archive_path: Path, status: str) -> None:
        data = asdict(metadata)
        gross_amount = data.get("gross_amount") if data.get("gross_amount") is not None else data["amount"]
        document_type = data.get("document_type") or ("invoice" if data["is_invoice"] else "document")
        transaction_type = _normalize_transaction_type(data.get("transaction_type"))
        invoice_date = data["invoice_date"]
        review_status = "reviewed" if status == "archived" else (data.get("review_status") or "needs_review")
        updated_at = datetime.utcnow().isoformat(timespec="seconds")
        self.connection.execute(
            """
            insert into invoices (
                file_hash, source_path, archive_path, is_invoice, confidence, vendor,
                invoice_date, amount, currency, invoice_number, category, status,
                reason, updated_at, source, original_filename, stored_path,
                document_type, transaction_type, year, month, net_amount, tax_amount,
                gross_amount, open_amount, paid_amount, is_business, is_tax_relevant, review_status,
                ai_confidence, ai_raw_json, created_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(file_hash) do update set
                source_path = excluded.source_path,
                archive_path = excluded.archive_path,
                is_invoice = excluded.is_invoice,
                confidence = excluded.confidence,
                vendor = excluded.vendor,
                invoice_date = excluded.invoice_date,
                amount = excluded.amount,
                currency = excluded.currency,
                invoice_number = excluded.invoice_number,
                category = excluded.category,
                status = excluded.status,
                reason = excluded.reason,
                updated_at = excluded.updated_at,
                source = excluded.source,
                original_filename = excluded.original_filename,
                stored_path = excluded.stored_path,
                document_type = excluded.document_type,
                transaction_type = excluded.transaction_type,
                year = excluded.year,
                month = excluded.month,
                net_amount = excluded.net_amount,
                tax_amount = excluded.tax_amount,
                gross_amount = excluded.gross_amount,
                open_amount = excluded.open_amount,
                paid_amount = excluded.paid_amount,
                is_business = excluded.is_business,
                is_tax_relevant = excluded.is_tax_relevant,
                review_status = excluded.review_status,
                ai_confidence = excluded.ai_confidence,
                ai_raw_json = excluded.ai_raw_json
            """,
            (
                data["file_hash"],
                data["source_path"],
                str(archive_path),
                int(data["is_invoice"]),
                data["confidence"],
                data["vendor"],
                invoice_date.isoformat(),
                gross_amount,
                data["currency"],
                data["invoice_number"],
                data["category"],
                status,
                data["reason"],
                updated_at,
                "agent",
                Path(data["source_path"]).name,
                str(archive_path),
                document_type,
                transaction_type,
                invoice_date.year,
                invoice_date.month,
                data.get("net_amount"),
                data.get("tax_amount"),
                gross_amount,
                data.get("open_amount"),
                data.get("paid_amount"),
                int(bool(data.get("is_business", True))),
                int(bool(data.get("is_tax_relevant", True))),
                review_status,
                data["confidence"],
                data.get("ai_raw_json") or "",
                updated_at,
            ),
        )
        self.connection.commit()

    def export_monthly_indexes(self, archive_dir: Path) -> list[Path]:
        rows = self.connection.execute(
            """
            select invoice_date, vendor, amount, currency, invoice_number, category,
                   source_path, archive_path, file_hash, confidence, status
            from invoices
            where is_invoice = 1
            order by invoice_date, vendor
            """
        ).fetchall()

        grouped: dict[tuple[int, int], list[sqlite3.Row]] = {}
        for row in rows:
            invoice_date = datetime.fromisoformat(row["invoice_date"]).date()
            grouped.setdefault((invoice_date.year, invoice_date.month), []).append(row)

        written = []
        for (year, month), month_rows in grouped.items():
            target_dir = month_dir_for(archive_dir, year, month)
            target_dir.mkdir(parents=True, exist_ok=True)
            xlsx_path = target_dir / "index.xlsx"
            _write_xlsx(xlsx_path, _rows_for_export(month_rows))
            written.append(xlsx_path)
        return written

    def _init_schema(self):
        self.connection.execute(
            """
            create table if not exists invoices (
                id integer primary key autoincrement,
                file_hash text not null unique,
                source_path text not null,
                archive_path text not null,
                is_invoice integer not null,
                confidence real not null,
                vendor text not null,
                invoice_date text not null,
                amount real,
                currency text not null,
                invoice_number text,
                category text not null,
                status text not null,
                reason text,
                updated_at text not null
            )
            """
        )
        self.connection.execute(
            """
            create table if not exists email_messages (
                id integer primary key autoincrement,
                message_key text not null unique,
                processed_at text not null
            )
            """
        )
        existing = {row["name"] for row in self.connection.execute("pragma table_info(invoices)").fetchall()}
        for column, definition in EXTRA_COLUMNS.items():
            if column not in existing:
                self.connection.execute(f"alter table invoices add column {column} {definition}")
        self.connection.execute(
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
        self.connection.commit()


def _rows_for_export(rows: Iterable[sqlite3.Row]) -> list[list[object]]:
    output = [list(HEADERS)]
    for row in rows:
        output.append(
            [
                row["invoice_date"],
                row["vendor"],
                row["net_amount"] if "net_amount" in row.keys() and row["net_amount"] is not None else "",
                row["tax_amount"] if "tax_amount" in row.keys() and row["tax_amount"] is not None else "",
                (row["gross_amount"] if "gross_amount" in row.keys() and row["gross_amount"] is not None else row["amount"]) or "",
                row["open_amount"] if "open_amount" in row.keys() and row["open_amount"] is not None else "",
                row["paid_amount"] if "paid_amount" in row.keys() and row["paid_amount"] is not None else "",
                row["currency"],
                row["invoice_number"] or "",
                row["document_type"] if "document_type" in row.keys() else "",
                row["transaction_type"] if "transaction_type" in row.keys() else "expense",
                row["category"],
                row["source_path"],
                row["archive_path"],
                row["file_hash"],
                f"{row['confidence']:.2f}",
                row["status"],
            ]
        )
    return output


def _write_xlsx(path: Path, rows: list[list[object]]) -> None:
    sheet_data = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            ref = f"{_column_name(col_index)}{row_index}"
            if isinstance(value, (int, float)) and value != "":
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        sheet_data.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_data)}</sheetData>'
        "</worksheet>"
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types_xml())
        zf.writestr("_rels/.rels", _rels_xml())
        zf.writestr("xl/workbook.xml", _workbook_xml())
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        zf.writestr("xl/worksheets/sheet1.xml", worksheet)


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _normalize_transaction_type(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"income", "einnahme", "revenue", "credit", "erstattung", "gutschrift"}:
        return "income"
    return "expense"


def _content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )


def _rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _workbook_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Rechnungen" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )


def _workbook_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
