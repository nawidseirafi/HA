import csv
import io
import zipfile
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape

from .service import InvoiceService


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
                if stored_path:
                    try:
                        document_path = self.invoice_service._resolve_document_path(stored_path)
                    except Exception:
                        continue
                    archive.write(document_path, arcname=document_path.name)
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
        zf.writestr("[Content_Types].xml", _content_types_xml())
        zf.writestr("_rels/.rels", _rels_xml())
        zf.writestr("xl/workbook.xml", _workbook_xml())
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        zf.writestr("xl/worksheets/sheet1.xml", worksheet)


def _write_simple_pdf(path: Path, title: str, rows: list[dict]) -> None:
    page_width = 842
    page_height = 595
    margin = 36
    row_height = 18
    rows_per_page = 22
    total = sum(_amount(row) for row in rows)
    pages = [rows[index:index + rows_per_page] for index in range(0, len(rows), rows_per_page)] or [[]]
    content_streams = [
        _pdf_page_content(
            title=title,
            rows=page_rows,
            page_number=page_index + 1,
            page_count=len(pages),
            total_rows=len(rows),
            total=total,
            page_width=page_width,
            page_height=page_height,
            margin=margin,
            row_height=row_height,
        )
        for page_index, page_rows in enumerate(pages)
    ]
    page_object_start = 3
    font_object_id = page_object_start + len(content_streams)
    content_object_start = font_object_id + 1
    kids = " ".join(f"{page_object_start + index} 0 R" for index in range(len(content_streams)))
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        f"2 0 obj << /Type /Pages /Kids [{kids}] /Count {len(content_streams)} >> endobj\n".encode(),
    ]
    for index in range(len(content_streams)):
        page_id = page_object_start + index
        content_id = content_object_start + index
        objects.append(
            (
                f"{page_id} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
                f"/Resources << /Font << /F1 {font_object_id} 0 R >> >> /Contents {content_id} 0 R >> endobj\n"
            ).encode()
        )
    objects.append(f"{font_object_id} 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n".encode())
    for index, stream in enumerate(content_streams):
        content = stream.encode("latin-1", errors="replace")
        content_id = content_object_start + index
        objects.append(
            f"{content_id} 0 obj << /Length {len(content)} >> stream\n".encode()
            + content
            + b"\nendstream endobj\n"
        )
    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n")
    offsets = []
    for obj in objects:
        offsets.append(buffer.tell())
        buffer.write(obj)
    xref = buffer.tell()
    buffer.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        buffer.write(f"{offset:010d} 00000 n \n".encode())
    buffer.write(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    path.write_bytes(buffer.getvalue())


def _pdf_page_content(
    *,
    title: str,
    rows: list[dict],
    page_number: int,
    page_count: int,
    total_rows: int,
    total: float,
    page_width: int,
    page_height: int,
    margin: int,
    row_height: int,
) -> str:
    commands = [
        "1 1 1 rg 0 0 842 595 re f",
        "0.08 0.12 0.2 rg 0 545 842 50 re f",
        _pdf_text(margin, 566, title, 18, "1 1 1"),
        _pdf_text(page_width - margin - 90, 566, f"Seite {page_number}/{page_count}", 9, "0.82 0.88 0.96"),
        _pdf_text(margin, 523, f"Belege: {total_rows}", 11, "0.12 0.18 0.28"),
        _pdf_text(margin + 130, 523, f"Summe brutto: {_format_money(total)}", 11, "0.12 0.18 0.28"),
        "0.88 0.91 0.96 rg 36 496 770 24 re f",
    ]
    columns = [
        ("Datum", 42, 64),
        ("Anbieter", 106, 178),
        ("Kategorie", 284, 106),
        ("Brutto", 390, 92),
        ("Art", 500, 64),
        ("Status", 578, 78),
        ("Rechnung", 670, 100),
    ]
    for label, x, _width in columns:
        commands.append(_pdf_text(x, 505, label, 8.5, "0.22 0.29 0.4"))

    y = 474
    for index, row in enumerate(rows):
        if index % 2 == 0:
            commands.append(f"0.97 0.98 1 rg 36 {y - 5} 770 {row_height} re f")
        commands.append("0.86 0.89 0.94 RG 36 %.1f m 806 %.1f l S" % (y - 7, y - 7))
        values = [
            _short(row.get("invoice_date"), 10),
            _short(row.get("vendor"), 30),
            _short(row.get("category"), 22),
            _format_money(_amount(row), row.get("currency") or "EUR"),
            "Einnahme" if row.get("transaction_type") == "income" else "Ausgabe",
            _short(row.get("review_status") or row.get("status"), 14),
            _short(row.get("invoice_number"), 22),
        ]
        for value, (_label, x, width) in zip(values, columns):
            align_right = _label == "Brutto"
            text_x = x + width - _text_width(value, 8.5) if align_right else x
            commands.append(_pdf_text(text_x, y, value, 8.5, "0.08 0.12 0.2"))
        y -= row_height

    if not rows:
        commands.append(_pdf_text(margin, 470, "Keine Belege fuer diesen Zeitraum.", 11, "0.35 0.42 0.52"))
    commands.append(_pdf_text(margin, 24, "RoboterSteve Invoice Export", 8, "0.45 0.52 0.62"))
    return "\n".join(commands)


def _pdf_text(x: float, y: float, value: object, size: float = 10, color: str = "0 0 0") -> str:
    return f"{color} rg BT /F1 {size} Tf {x:.1f} {y:.1f} Td ({_pdf_escape(str(value or ''))}) Tj ET"


def _amount(row: dict) -> float:
    try:
        return float(row.get("gross_amount") or row.get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def _format_money(value: float, currency: str = "EUR") -> str:
    return f"{value:,.2f} {currency}".replace(",", "X").replace(".", ",").replace("X", ".")


def _short(value: object, max_length: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= max_length else f"{text[:max_length - 1]}."


def _text_width(value: str, font_size: float) -> float:
    return len(value) * font_size * 0.48


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("\n", "\\n")


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )


def _rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )


def _workbook_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Rechnungen" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )


def _workbook_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
