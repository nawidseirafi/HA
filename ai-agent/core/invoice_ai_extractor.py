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
        amount = _parse_amount(data.get("amount"))
        confidence = float(data.get("confidence", metadata.confidence))
    except (TypeError, ValueError):
        logging.info("KI-Belegextraktion hatte ungueltige Werte: %s", data)
        return metadata

    vendor = _clean_text(data.get("vendor")) or metadata.vendor
    currency = (_clean_text(data.get("currency")) or metadata.currency or "EUR").upper()
    invoice_number = _clean_text(data.get("invoice_number")) or metadata.invoice_number
    category = _clean_text(data.get("category")) or metadata.category or default_category
    is_invoice = bool(data.get("is_invoice", True))
    reason = _clean_text(data.get("reason")) or "KI-Belegextraktion"
    confidence = max(0.0, min(confidence, 1.0))

    return replace(
        metadata,
        is_invoice=is_invoice,
        confidence=max(metadata.confidence, confidence),
        vendor=vendor,
        invoice_date=invoice_date,
        amount=amount if amount is not None else metadata.amount,
        currency=currency,
        invoice_number=invoice_number,
        category=category,
        reason=f"{metadata.reason}; ai:{reason}",
    )


def _build_prompt(path: Path, metadata: InvoiceMetadata, default_category: str) -> str:
    return f"""
Analysiere diesen Beleg oder diese Rechnung.

Extrahiere:
- is_invoice: boolean
- vendor: Anbieter/Haendler, kurz und menschlich lesbar
- invoice_date: Datum im Format YYYY-MM-DD
- amount: Endbetrag/zu zahlender Bruttobetrag als Zahl mit Punkt, nicht MwSt/Netto/Uhrzeit
- currency: ISO-Code, normalerweise EUR
- invoice_number: Rechnungsnummer falls vorhanden, sonst leerer String
- category: eine Kategorie, z.B. KFZ, Telekommunikation, Webhosting, Versicherung, Gesundheit, Bewirtung, Reisekosten, Versorgung, Steuer, Immobilie, Review oder {default_category}
- confidence: Zahl zwischen 0 und 1
- reason: kurzer Grund fuer die Entscheidung

Wichtige Regeln:
- Bei Tankstelle, Kraftstoff, Benzin, Diesel, Aral, Shell, Esso, Jet, Star, HEM, TotalEnergies: category = "KFZ".
- Verwende bei Belegen den TOTAL/Gesamt/Brutto/Kartenzahlungs-Betrag als amount.
- Verwende keine Uhrzeit aus dem Dateinamen als amount.
- Wenn der Beleg nicht sicher lesbar ist, setze is_invoice=false und category="Review".

Dateiname: {path.name}
Lokale Voranalyse:
vendor={metadata.vendor}
invoice_date={metadata.invoice_date.isoformat()}
amount={metadata.amount}
currency={metadata.currency}
category={metadata.category}
confidence={metadata.confidence}
reason={metadata.reason}

JSON-Schema:
{{
  "is_invoice": true,
  "vendor": "Tankstelle",
  "invoice_date": "2026-05-20",
  "amount": 111.98,
  "currency": "EUR",
  "invoice_number": "",
  "category": "KFZ",
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
