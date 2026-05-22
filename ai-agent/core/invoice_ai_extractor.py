import json
import logging
import re
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any, Optional

from core.invoice_extractor import InvoiceMetadata


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
    response = llm_client.generate_with_file(str(path), prompt=prompt, system=SYSTEM_PROMPT)
    data = _parse_json(response.text)

    if not data:
        logging.info("KI-Belegextraktion lieferte kein JSON: %s", response.text[:500])
        return metadata

    try:
        invoice_date = _parse_date(data.get("invoice_date")) or metadata.invoice_date
        gross_amount = _parse_amount(data.get("gross_amount", data.get("amount")))
        net_amount = _parse_amount(data.get("net_amount"))
        tax_amount = _parse_amount(data.get("tax_amount"))
        confidence = float(data.get("confidence", metadata.confidence))
    except (TypeError, ValueError):
        logging.info("KI-Belegextraktion hatte ungueltige Werte: %s", data)
        return metadata

    vendor = _clean_text(data.get("vendor")) or metadata.vendor
    currency = (_clean_text(data.get("currency")) or metadata.currency or "EUR").upper()
    invoice_number = _clean_text(data.get("invoice_number")) or metadata.invoice_number
    category = _clean_text(data.get("category")) or metadata.category or default_category
    document_type = _normalize_document_type(data.get("document_type"), data.get("is_invoice"))
    transaction_type = _normalize_transaction_type(data.get("transaction_type"))
    is_invoice = document_type in {"invoice", "receipt", "credit_note", "payroll", "assessment", "certificate", "statement"}
    is_business = _parse_bool(data.get("is_business"), metadata.is_business)
    is_tax_relevant = _parse_bool(data.get("is_tax_relevant"), metadata.is_tax_relevant)
    reason = _clean_text(data.get("reason")) or "KI-Belegextraktion"
    confidence = max(0.0, min(confidence, 1.0))
    amount = gross_amount if gross_amount is not None else metadata.amount
    review_status = "needs_review" if confidence < 0.9 or document_type in {"document", "unknown"} else "reviewed"

    return replace(
        metadata,
        is_invoice=is_invoice,
        confidence=max(metadata.confidence, confidence),
        vendor=vendor,
        invoice_date=invoice_date,
        amount=amount,
        currency=currency,
        invoice_number=invoice_number,
        category=category,
        reason=f"{metadata.reason}; ai:{reason}",
        document_type=document_type,
        transaction_type=transaction_type,
        net_amount=net_amount,
        tax_amount=tax_amount,
        gross_amount=amount,
        is_business=is_business,
        is_tax_relevant=is_tax_relevant,
        review_status=review_status,
        ai_raw_json=json.dumps(data, ensure_ascii=False, sort_keys=True),
    )


def _build_prompt(path: Path, metadata: InvoiceMetadata, default_category: str) -> str:
    return f"""
Analysiere dieses Dokument fuer Buchhaltung und Steuer-Vorsortierung.

Das Dokument kann eine Rechnung, ein Kassenbeleg, eine Quittung, ein Bescheid, eine Lohn-/Gehaltsabrechnung, eine Lohnsteuerbescheinigung, eine Gutschrift, ein Konto-/Versicherungs-/Steuerdokument oder ein sonstiger Nachweis sein.

Extrahiere:
- document_type: einer von invoice, receipt, assessment, payroll, certificate, credit_note, statement, contract, document, unknown
- is_invoice: boolean; true fuer buchhalterisch relevante Belege/Nachweise, false nur bei unlesbaren oder irrelevanten Dokumenten
- transaction_type: income oder expense aus Sicht des Nutzers
- vendor: Anbieter/Haendler/Absender/Arbeitgeber/Behoerde, kurz und menschlich lesbar
- invoice_date: relevantes Dokumentdatum im Format YYYY-MM-DD
- net_amount: Nettobetrag als Zahl mit Punkt, falls vorhanden, sonst null
- tax_amount: MwSt/USt/Steuerbetrag als Zahl mit Punkt, falls vorhanden, sonst null
- gross_amount: Endbetrag/Brutto/Zahlbetrag als Zahl mit Punkt, nicht Uhrzeit/Datum
- amount: identisch zu gross_amount fuer Rueckwaertskompatibilitaet
- currency: ISO-Code, normalerweise EUR
- invoice_number: Rechnungsnummer/Aktenzeichen/Referenz falls vorhanden, sonst leerer String
- category: eine Kategorie, z.B. KFZ, Telekommunikation, Webhosting, Versicherung, Gesundheit, Bewirtung, Reisekosten, Versorgung, Steuer, Immobilie, Gehalt, Einnahmen, Review oder {default_category}
- is_business: boolean; true wenn beruflich/steuerlich relevant plausibel ist
- is_tax_relevant: boolean; true wenn fuer Steuer/Archiv relevant plausibel ist
- confidence: Zahl zwischen 0 und 1
- reason: kurzer Grund fuer die Entscheidung

Wichtige Regeln:
- transaction_type = "expense" fuer Rechnungen, Kassenbelege, Ausgaben, Versicherungen, Strom, Telekommunikation, KFZ, Gesundheit, Steuerzahlungen.
- transaction_type = "income" fuer Gehaltsabrechnungen, Lohnscheine, Lohnsteuerbescheinigungen, Gutschriften, Erstattungen, Einnahmen, Zahlungseingaenge.
- Bei Tankstelle, Kraftstoff, Benzin, Diesel, Aral, Shell, Esso, Jet, Star, HEM, TotalEnergies: category = "KFZ".
- Bei Lohn-/Gehaltsabrechnung oder Lohnsteuerbescheinigung: document_type = "payroll" oder "certificate", transaction_type = "income", category = "Gehalt".
- Bei Steuerbescheid: document_type = "assessment", category = "Steuer", transaction_type nach Geldfluss: Nachzahlung expense, Erstattung income.
- Verwende bei Belegen den TOTAL/Gesamt/Brutto/Kartenzahlungs-Betrag als gross_amount und amount.
- Verwende keine Uhrzeit, Kundennummer, PLZ, Datum oder Rechnungsnummer als Betrag.
- Wenn kein sicherer Betrag erkennbar ist, setze gross_amount und amount auf null.
- Wenn das Dokument nicht sicher lesbar ist, setze document_type="unknown", is_invoice=false, category="Review", confidence <= 0.4.
- Antworte ausschliesslich als einzelnes JSON-Objekt ohne Markdown.

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
  "document_type": "receipt",
  "is_invoice": true,
  "transaction_type": "expense",
  "vendor": "Tankstelle",
  "invoice_date": "2026-05-20",
  "net_amount": 94.10,
  "tax_amount": 17.88,
  "gross_amount": 111.98,
  "amount": 111.98,
  "currency": "EUR",
  "invoice_number": "",
  "category": "KFZ",
  "is_business": true,
  "is_tax_relevant": true,
  "confidence": 0.95,
  "reason": "TOTAL 111,98 EUR erkannt"
}}
""".strip()


def _parse_json(text: str) -> Optional[dict[str, Any]]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
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
    match = re.search(r"\d+(?:\.\d{1,2})?", text)
    if not match:
        return None
    return float(match.group(0))


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _normalize_transaction_type(value: Any) -> str:
    text = _clean_text(value).lower()
    if text in {"income", "einnahme", "revenue", "credit", "erstattung", "gutschrift"}:
        return "income"
    return "expense"


def _normalize_document_type(value: Any, is_invoice_value: Any = None) -> str:
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
    allowed = {"invoice", "receipt", "assessment", "payroll", "certificate", "credit_note", "statement", "contract", "document", "unknown"}
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
