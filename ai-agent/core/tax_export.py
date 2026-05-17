import csv
import sqlite3
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape


DEFAULT_CATEGORY_RULES = {
    "all inkl": "Webhosting",
    "all-inkl": "Webhosting",
    "apotheke": "Gesundheit",
    "arzt": "Gesundheit",
    "artz": "Gesundheit",
    "auto": "KFZ",
    "autoversicherung": "Versicherung",
    "congstar": "Telekommunikation",
    "elster": "Steuer",
    "finanzamt": "Steuer",
    "gebäudeversicherung": "Versicherung",
    "gebaeudeversicherung": "Versicherung",
    "grundbesitz": "Immobilie",
    "hausrat": "Versicherung",
    "hotel": "Reisekosten",
    "huk24": "Versicherung",
    "kfz": "KFZ",
    "lkh": "Versicherung",
    "restaurant": "Bewirtung",
    "rechtschutz": "Versicherung",
    "rechtsschutz": "Versicherung",
    "sc technology": "Beratung/Abrechnung",
    "strato": "Webhosting",
    "strom": "Versorgung",
    "tankbeleg": "KFZ",
    "tankbelege": "KFZ",
    "vodafone": "Telekommunikation",
    "wasser": "Versorgung",
    "zahn": "Gesundheit",
    "zahnarzt": "Gesundheit",
}

REVIEW_KEYWORDS = (
    "angebot",
    "anordnung",
    "betriebsprüfung",
    "bescheinigung",
    "elster",
    "login",
    "meldebescheinigung",
    "lohnsteuerbescheinigung",
    "uvg",
)

DETAIL_HEADERS = (
    "Datum",
    "Anbieter",
    "Betrag",
    "Waehrung",
    "Steuerkategorie",
    "Hinweis",
    "Status",
    "Rechnungsnummer",
    "Archivpfad",
    "Quelle",
)

SUMMARY_HEADERS = ("Steuerkategorie", "Anzahl", "Summe EUR")
REVIEW_HEADERS = DETAIL_HEADERS


@dataclass
class TaxExportConfig:
    database_path: Path
    output_dir: Path
    category_rules: dict[str, str]


@dataclass
class TaxExportResult:
    year: int
    rows: int
    review_rows: int
    csv_path: Path
    xlsx_path: Path


def export_tax_year(config: TaxExportConfig, year: int) -> TaxExportResult:
    rows = _load_invoice_rows(config.database_path, year)
    categorized = [_categorize(row, config.category_rules) for row in rows]

    year_dir = config.output_dir / str(year)
    year_dir.mkdir(parents=True, exist_ok=True)
    csv_path = year_dir / f"einkommensteuer_{year}.csv"
    xlsx_path = year_dir / f"einkommensteuer_{year}.xlsx"

    detail_rows = [DETAIL_HEADERS] + [_detail_row(row) for row in categorized]
    summary_rows = [SUMMARY_HEADERS] + _summary_rows(categorized)
    review_rows = [REVIEW_HEADERS] + [_detail_row(row) for row in categorized if row["tax_category"] == "Review"]

    _write_csv(csv_path, detail_rows)
    _write_xlsx(
        xlsx_path,
        {
            "Alle Belege": detail_rows,
            "Summen": summary_rows,
            "Review": review_rows,
        },
    )

    return TaxExportResult(
        year=year,
        rows=len(categorized),
        review_rows=len(review_rows) - 1,
        csv_path=csv_path,
        xlsx_path=xlsx_path,
    )


def _load_invoice_rows(database_path: Path, year: int) -> list[sqlite3.Row]:
    con = sqlite3.connect(database_path)
    con.row_factory = sqlite3.Row
    try:
        return con.execute(
            """
            select invoice_date, vendor, amount, currency, invoice_number, status,
                   source_path, archive_path, category, reason
            from invoices
            where substr(invoice_date, 1, 4) = ?
            order by invoice_date, vendor
            """,
            (str(year),),
        ).fetchall()
    finally:
        con.close()


def _categorize(row: sqlite3.Row, rules: dict[str, str]) -> dict:
    text = " ".join(
        str(row[key] or "")
        for key in ("vendor", "source_path", "archive_path", "category", "reason")
    ).lower()

    tax_category = ""
    note = ""
    for keyword, category in rules.items():
        if keyword.lower() in text:
            tax_category = category
            note = f"Regel: {keyword}"
            break

    if not tax_category:
        tax_category = "Review"
        note = "Keine Regel gefunden"

    if row["status"] != "archived":
        tax_category = "Review"
        note = f"Status: {row['status']}"

    if row["amount"] is None:
        tax_category = "Review"
        note = "Betrag fehlt"

    if any(keyword in text for keyword in REVIEW_KEYWORDS):
        tax_category = "Review"
        note = "Review-Schluesselwort"

    return {
        "invoice_date": row["invoice_date"],
        "vendor": row["vendor"],
        "amount": row["amount"],
        "currency": row["currency"],
        "invoice_number": row["invoice_number"] or "",
        "status": row["status"],
        "source_path": row["source_path"],
        "archive_path": row["archive_path"],
        "tax_category": tax_category,
        "note": note,
    }


def _detail_row(row: dict) -> list[object]:
    return [
        row["invoice_date"],
        row["vendor"],
        row["amount"] if row["amount"] is not None else "",
        row["currency"],
        row["tax_category"],
        row["note"],
        row["status"],
        row["invoice_number"],
        row["archive_path"],
        row["source_path"],
    ]


def _summary_rows(rows: Iterable[dict]) -> list[list[object]]:
    grouped: dict[str, dict[str, float]] = {}
    for row in rows:
        if row["currency"] != "EUR" or row["amount"] is None:
            continue
        bucket = grouped.setdefault(row["tax_category"], {"count": 0, "sum": 0.0})
        bucket["count"] += 1
        bucket["sum"] += float(row["amount"])

    output = []
    for category in sorted(grouped):
        bucket = grouped[category]
        output.append([category, bucket["count"], round(bucket["sum"], 2)])
    return output


def _write_csv(path: Path, rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerows(rows)


def _write_xlsx(path: Path, sheets: dict[str, list[list[object]]]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types_xml(len(sheets)))
        zf.writestr("_rels/.rels", _rels_xml())
        zf.writestr("xl/workbook.xml", _workbook_xml(list(sheets)))
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(sheets)))
        for index, rows in enumerate(sheets.values(), start=1):
            zf.writestr(f"xl/worksheets/sheet{index}.xml", _worksheet_xml(rows))


def _worksheet_xml(rows: list[list[object]]) -> str:
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
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_data)}</sheetData>'
        "</worksheet>"
    )


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _content_types_xml(sheet_count: int) -> str:
    overrides = [
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    ]
    for index in range(1, sheet_count + 1):
        overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'{"".join(overrides)}'
        "</Types>"
    )


def _rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _workbook_xml(sheet_names: list[str]) -> str:
    sheets = []
    for index, name in enumerate(sheet_names, start=1):
        sheets.append(f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{"".join(sheets)}</sheets>'
        "</workbook>"
    )


def _workbook_rels_xml(sheet_count: int) -> str:
    relationships = []
    for index in range(1, sheet_count + 1):
        relationships.append(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{"".join(relationships)}'
        "</Relationships>"
    )
