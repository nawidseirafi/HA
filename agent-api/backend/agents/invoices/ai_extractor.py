import json
import logging
import re
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any, Optional

from invoices.extractor import InvoiceMetadata


SYSTEM_PROMPT = (
    "Du bist ein Rechnungs- und Beleg-Extraktor. "
    "Gib ausschliesslich gueltiges JSON ohne Markdown zurueck."
)


def refine_metadata_with_ai(
    path: Path,
    metadata: InvoiceMetadata,
    llm_client,
    default_category: str,
) -> InvoiceMetadata:
    prompt = _build_prompt(path, metadata, default_category)
    response = llm_client.generate_with_file(
        str(path),
        prompt=prompt,
        system=SYSTEM_PROMPT,
    )

    data = _parse_json(response.text)

    if not data:
        logging.info(
            "KI-Belegextraktion lieferte kein JSON: %s",
            response.text[:500],
        )
        return metadata

    try:
        invoice_date = (
            _parse_date(data.get("invoice_date"))
            or metadata.invoice_date
        )

        gross_amount = _parse_amount(
            data.get("gross_amount", data.get("amount"))
        )

        open_amount = _parse_amount(data.get("open_amount"))
        paid_amount = _parse_amount(data.get("paid_amount"))

        net_amount = _parse_amount(data.get("net_amount"))
        tax_amount = _parse_amount(data.get("tax_amount"))

        confidence = float(
            data.get("confidence", metadata.confidence)
        )

    except (TypeError, ValueError):
        logging.info(
            "KI-Belegextraktion hatte ungueltige Werte: %s",
            data,
        )
        return metadata

    vendor = (
        _clean_text(data.get("vendor"))
        or metadata.vendor
    )

    currency = (
        _clean_text(data.get("currency"))
        or metadata.currency
        or "EUR"
    ).upper()

    invoice_number = (
        _clean_text(data.get("invoice_number"))
        or metadata.invoice_number
    )

    category = (
        _clean_text(data.get("category"))
        or metadata.category
        or default_category
    )

    document_type = _normalize_document_type(
        data.get("document_type"),
        data.get("is_invoice"),
    )

    transaction_type = _normalize_transaction_type(
        data.get("transaction_type")
    )

    is_invoice = document_type in {
        "invoice",
        "receipt",
        "credit_note",
        "payroll",
        "assessment",
        "certificate",
        "statement",
    }

    is_business = _parse_bool(
        data.get("is_business"),
        metadata.is_business,
    )

    is_tax_relevant = _parse_bool(
        data.get("is_tax_relevant"),
        metadata.is_tax_relevant,
    )

    reason = (
        _clean_text(data.get("reason"))
        or "KI-Belegextraktion"
    )

    confidence = max(0.0, min(confidence, 1.0))
    if gross_amount is None:
        gross_amount = metadata.gross_amount if metadata.gross_amount is not None else metadata.amount

    #
    # WICHTIGE BETRAGSLOGIK
    #

    # KI liefert 0 EUR obwohl lokale OCR schon Betrag erkannt hat
    if (
        gross_amount == 0
        and metadata.amount is not None
        and metadata.amount > 0
        and document_type in {
            "invoice",
            "receipt",
            "assessment",
            "statement",
        }
    ):
        gross_amount = metadata.amount

        reason = (
            f"{reason}; "
            f"0-Betrag der KI ignoriert, "
            f"lokale Voranalyse hatte {metadata.amount}"
        )

    # Keine offenen/bezahlt-Betraege erfinden. Wenn die KI diese Felder nicht
    # sicher liefert, bleiben sie leer statt scheinbar korrekt zu wirken.
    if open_amount is None:
        open_amount = metadata.open_amount

    # paid_amount fallback
    if paid_amount is None:
        paid_amount = metadata.paid_amount

    review_status = (
        "needs_review"
        if confidence < 0.9
        or document_type in {"document", "unknown"}
        else "reviewed"
    )

    return replace(
        metadata,
        is_invoice=is_invoice,
        confidence=max(metadata.confidence, confidence),
        vendor=vendor,
        invoice_date=invoice_date,

        #
        # BETRAGSFELDER
        #

        # Voller Rechnungsbetrag
        gross_amount=gross_amount,

        # Rueckwaertskompatibilitaet
        amount=gross_amount,

        # Neu
        open_amount=open_amount,
        paid_amount=paid_amount,

        #
        # Weitere Felder
        #

        currency=currency,
        invoice_number=invoice_number,
        category=category,
        reason=f"{metadata.reason}; ai:{reason}",
        document_type=document_type,
        transaction_type=transaction_type,
        net_amount=net_amount,
        tax_amount=tax_amount,
        is_business=is_business,
        is_tax_relevant=is_tax_relevant,
        review_status=review_status,
        ai_raw_json=json.dumps(
            data,
            ensure_ascii=False,
            sort_keys=True,
        ),
    )


def _build_prompt(
    path: Path,
    metadata: InvoiceMetadata,
    default_category: str,
) -> str:
    return f"""
Analysiere dieses Dokument fuer Buchhaltung und Steuer-Vorsortierung.

Das Dokument kann eine Rechnung, ein Kassenbeleg, eine Quittung, ein Bescheid, eine Lohn-/Gehaltsabrechnung, eine Lohnsteuerbescheinigung, eine Gutschrift, ein Konto-/Versicherungs-/Steuerdokument oder ein sonstiger Nachweis sein.

Extrahiere:
- document_type: einer von invoice, receipt, assessment, payroll, certificate, credit_note, statement, contract, document, unknown
- is_invoice: boolean
- transaction_type: income oder expense
- vendor
- invoice_date
- net_amount
- tax_amount

- gross_amount:
  Voller Rechnungs-/Bruttobetrag vor Verrechnung.

- open_amount:
  Tatsächlich noch offener Zahlbetrag.

- paid_amount:
  Bereits bezahlter/verrechneter Betrag.

- amount:
  identisch zu gross_amount fuer Rueckwaertskompatibilitaet

- currency
- invoice_number
- category
- is_business
- is_tax_relevant
- confidence
- reason

WICHTIGE REGELN:

- Rechnungsbetrag != offener Zahlbetrag

Wenn gleichzeitig vorkommen:
- Rechnungsbetrag
- abzueglich Vorschuesse
- bereits bezahlt
- zu zahlender Betrag 0,00

Dann:
- gross_amount = voller Rechnungsbetrag
- open_amount = 0.00
- paid_amount = voller Rechnungsbetrag
- transaction_type = expense
- KEINE credit_note

Das Wort:
- gutgeschrieben
- abgetreten
- schuldbefreiend

bedeutet NICHT automatisch:
- credit_note
- income

Bei Steuerberater, Steuerberatung, StBVV,
Finanzbuchhaltung oder Buchhaltung:
- category = Steuer
- transaction_type = expense
- document_type = invoice

BETRAGSPRIORITAET:
1. Rechnungsbetrag
2. Gesamtbetrag
3. Bruttobetrag
4. Endbetrag
5. Total
6. Kartenzahlung
7. Zu zahlen

IGNORIEREN:
- Restforderung
- Vorschuesse
- verrechnet
- Saldo
- Kontostand
- Zwischensummen

Wenn Dokument unlesbar:
- document_type = unknown
- confidence <= 0.4

Antworte ausschliesslich als JSON.

Dateiname: {path.name}

Lokale Voranalyse:
vendor={metadata.vendor}
invoice_date={metadata.invoice_date.isoformat()}
amount={metadata.amount}
currency={metadata.currency}
category={metadata.category}
document_type={metadata.document_type}
transaction_type={metadata.transaction_type}
confidence={metadata.confidence}
reason={metadata.reason}

JSON-Schema:
{{
  "document_type": "invoice",
  "is_invoice": true,
  "transaction_type": "expense",
  "vendor": "Steuerberater",
  "invoice_date": "2026-05-20",
  "net_amount": 1940.40,
  "tax_amount": 368.68,
  "gross_amount": 2309.08,
  "open_amount": 0.00,
  "paid_amount": 2309.08,
  "amount": 2309.08,
  "currency": "EUR",
  "invoice_number": "12345",
  "category": "Steuer",
  "is_business": true,
  "is_tax_relevant": true,
  "confidence": 0.95,
  "reason": "Rechnung mit verrechneten Vorschuessen"
}}
""".strip()


def _parse_json(text: str) -> Optional[dict[str, Any]]:
    cleaned = text.strip()

    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
    )

    try:
        value = json.loads(cleaned)

    except json.JSONDecodeError:
        match = re.search(
            r"\{.*\}",
            cleaned,
            flags=re.DOTALL,
        )

        if not match:
            return None

        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    if isinstance(value, dict):
        return value

    return None


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None

    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_amount(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()

    if "," in text:
        text = text.replace(".", "").replace(",", ".")

    match = re.search(
        r"-?\d+(?:\.\d{1,2})?",
        text,
    )

    if not match:
        return None

    return float(match.group(0))


def _clean_text(value: Any) -> str:
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def _normalize_transaction_type(value: Any) -> str:
    text = _clean_text(value).lower()

    if text in {
        "income",
        "einnahme",
        "revenue",
        "credit",
        "erstattung",
        "gutschrift",
    }:
        return "income"

    return "expense"


def _normalize_document_type(
    value: Any,
    is_invoice_value: Any = None,
) -> str:
    text = _clean_text(value).lower()

    aliases = {
        "rechnung": "invoice",
        "kassenbeleg": "receipt",
        "beleg": "receipt",
        "quittung": "receipt",
        "bescheid": "assessment",
        "steuerbescheid": "assessment",
        "lohnschein": "payroll",
        "gehaltsabrechnung": "payroll",
        "lohnabrechnung": "payroll",
        "lohnsteuerbescheinigung": "certificate",
        "bescheinigung": "certificate",
        "gutschrift": "credit_note",
        "kontoauszug": "statement",
        "vertrag": "contract",
        "dokument": "document",
    }

    allowed = {
        "invoice",
        "receipt",
        "assessment",
        "payroll",
        "certificate",
        "credit_note",
        "statement",
        "contract",
        "document",
        "unknown",
    }

    if text in allowed:
        return text

    if text in aliases:
        return aliases[text]

    if is_invoice_value is False:
        return "unknown"

    return "invoice"


def _parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value

    if value is None:
        return default

    text = str(value).strip().lower()

    if text in {"1", "true", "yes", "ja", "y"}:
        return True

    if text in {"0", "false", "no", "nein", "n"}:
        return False

    return default
