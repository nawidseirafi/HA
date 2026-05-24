import csv
import io
import zipfile
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape

from api.invoice.service import InvoiceService

EXPORT_HEADERS = [
    "Datum",
    "Anbieter",
    "Kategorie",
    "Betrag Netto",
    "MwSt",
    "Betrag Brutto",
    "Art",
    "Waehrung",
    "Rechnungsnummer",
    "Zahlungsart",
    "Status",
    "Quelle",
]

class ExportService:
    def __init__(self, invoice_service: Optional[InvoiceService] = None):
        self.invoice_service = invoice_service or InvoiceService()
        self.export_dir = self.invoice_service.export_dir
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def excel(self, year: int, month: Optional[int] = None) -> Path:
        rows = self.invoice_service.rows_for_period(year, month)
        path = self._target_path(year, month, "xlsx")
        _write_xlsx(path, [EXPORT_HEADERS, *[_invoice_row(row) for row in rows]])
        return path

    def pdf_summary(self, year: int, month: Optional[int] = None) -> Path:
        rows = self.invoice_service.rows_for_period(year, month)
        path = self._target_path(year, month, "pdf")
        title = f"Rechnungen {year}" if month is None else f"Rechnungen {month:02d}/{year}"
        _write_simple_pdf(path, title, rows)
        return path

    def zip_documents(self, year: int, month: Optional[int] = None) -> Path:
        rows = self.invoice_service.rows_for_period(year, month)
        path = self._target_path(year, month, "zip")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow(EXPORT_HEADERS)
            for row in rows:
                writer.writerow(_invoice_row(row))
                stored_path = row.get("stored_path") or row.get("archive_path") or row.get("source_path")
                if stored_path and Path(stored_path).exists():
                    archive.write(stored_path, arcname=Path(stored_path).name)
            archive.writestr("index.csv", csv_buffer.getvalue())
        return path

    def _target_path(self, year: int, month: Optional[int], extension: str) -> Path:
        stem = f"invoices-{year}" if month is None else f"invoices-{year}-{month:02d}"
        return self.export_dir / f"{stem}.{extension}"

def _invoice_row(row: dict) -> list[object]:
    return [
        row.get("invoice_date") or "",
        row.get("vendor") or "",
        row.get("category") or "",
        row.get("net_amount") or "",
        row.get("tax_amount") or "",
        row.get("gross_amount") or row.get("amount") or "",
        "Einnahme" if row.get("transaction_type") == "income" else "Ausgabe",
        row.get("currency") or "EUR",
        row.get("invoice_number") or "",
        row.get("payment_method") or "",
        row.get("review_status") or row.get("status") or "",
        row.get("source") or row.get("source_path") or "",
    ]

def _write_xlsx(path: Path, rows: list[list[object]]) -> None:
    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            ref = f"{_column_name(column_index)}{row_index}"
            if isinstance(value, (int, float)) and value != "":
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        '</worksheet>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        # ...existing code...
        pass
