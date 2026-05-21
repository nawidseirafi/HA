import hashlib
import logging
import re
import subprocess
import string
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp")


INVOICE_KEYWORDS = (
    "rechnung",
    "invoice",
    "receipt",
    "quittung",
    "beleg",
    "abrechnung",
    "gutschrift",
)

REVIEW_KEYWORDS = (
    "lohnsteuerbescheinigung",
    "meldebescheinigung",
)

KNOWN_INVOICE_VENDORS = (
    "all-inkl",
    "all inkl",
    "amazon",
    "amazon eu",
    "apotheke",
    "autoversicherung",
    "carwash",
    "congstar",
    "aral",
    "avia",
    "esso",
    "gebäudeversicherung",
    "gebaudeversicherung",
    "grundbesitz",
    "hausrat",
    "hem",
    "hotel",
    "huk24",
    "iphone",
    "jet",
    "kfz",
    "lkh",
    "porsche",
    "porsche zentrum",
    "restaurant",
    "rechtschutz",
    "rechtsschutz",
    "strato",
    "strom",
    "shell",
    "star",
    "tankbeleg",
    "tankbelege",
    "tankstelle",
    "telekom",
    "totalenergies",
    "vodafone",
    "wasser",
    "zahn",
    "zahnarzt",
)

KNOWN_VENDOR_CATEGORIES = {
    "aral": "KFZ",
    "avia": "KFZ",
    "esso": "KFZ",
    "hem": "KFZ",
    "jet": "KFZ",
    "kraftstoff": "KFZ",
    "porsche": "KFZ",
    "porsche zentrum": "KFZ",
    "shell": "KFZ",
    "star": "KFZ",
    "tankbeleg": "KFZ",
    "tankbelege": "KFZ",
    "tankstelle": "KFZ",
    "totalenergies": "KFZ",
}

MONTH_WORDS = {
    "januar": 1,
    "jan": 1,
    "februar": 2,
    "feb": 2,
    "maerz": 3,
    "märz": 3,
    "marz": 3,
    "april": 4,
    "apr": 4,
    "mai": 5,
    "juni": 6,
    "jun": 6,
    "juli": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "oktober": 10,
    "okt": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "dezember": 12,
    "dez": 12,
    "dec": 12,
}


@dataclass
class InvoiceMetadata:
    source_path: str
    file_hash: str
    is_invoice: bool
    confidence: float
    vendor: str
    invoice_date: date
    amount: Optional[float]
    currency: str
    invoice_number: str
    category: str
    reason: str


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_metadata(path: Path, default_category: str = "Unsortiert") -> InvoiceMetadata:
    file_hash = file_sha256(path)
    filename_text = _normalize_text(path.stem)
    body_text = _read_lightweight_text(path)
    body_text_normalized = _normalize_text(body_text)
    combined = f"{filename_text} {body_text_normalized}".strip()
    content_text = body_text_normalized if _has_meaningful_text(body_text_normalized) else ""

    keyword_hits = _keyword_hits(INVOICE_KEYWORDS, combined)
    vendor_hits = _keyword_hits(KNOWN_INVOICE_VENDORS, combined)
    review_hits = _keyword_hits(REVIEW_KEYWORDS, combined)
    invoice_date = _find_best_date(path, combined)
    amount, currency = _find_amount(content_text or filename_text)
    if not content_text and _looks_like_upload_filename(filename_text):
        amount, currency = None, "EUR"
    invoice_number = _find_invoice_number(combined)
    vendor = _find_vendor(path.stem, invoice_date, vendor_hits)
    category = _find_category(vendor_hits, default_category)

    confidence = 0.0
    reasons = []
    if keyword_hits:
        confidence += 0.45
        reasons.append("keyword:" + ",".join(keyword_hits[:3]))
    if vendor_hits:
        confidence += 0.25
        reasons.append("known_vendor:" + ",".join(vendor_hits[:3]))
    if invoice_date:
        confidence += 0.25
        reasons.append("date")
    if amount is not None:
        confidence += 0.2
        reasons.append("amount")
    if invoice_number:
        confidence += 0.1
        reasons.append("invoice_number")

    ext = path.suffix.lower()
    if ext in (".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"):
        confidence += 0.05

    confidence = min(confidence, 1.0)
    is_invoice = confidence >= 0.5
    if review_hits:
        confidence = min(confidence, 0.3)
        is_invoice = False
        reasons.append("review_keyword:" + ",".join(review_hits[:3]))
    if not content_text and _looks_like_upload_filename(filename_text):
        confidence = min(confidence, 0.3)
        is_invoice = False
        reasons.append("no_readable_text")

    return InvoiceMetadata(
        source_path=str(path),
        file_hash=file_hash,
        is_invoice=is_invoice,
        confidence=confidence,
        vendor=vendor,
        invoice_date=invoice_date,
        amount=amount,
        currency=currency,
        invoice_number=invoice_number,
        category=category,
        reason="; ".join(reasons) if reasons else "no invoice signals found",
    )


def _normalize_text(value: str) -> str:
    return value.lower().replace("_", " ").replace("-", " ")


def _looks_like_upload_filename(text: str) -> bool:
    return bool(
        re.search(r"\b20\d{6}t\d{6}z\b", text)
        or re.search(r"\b[a-f0-9]{24,}\b", text)
        or re.search(r"\b[0-9a-f]{8} [0-9a-f]{4} [0-9a-f]{4}", text)
    )


def _keyword_hits(keywords: tuple[str, ...], text: str) -> list[str]:
    hits = []
    for keyword in keywords:
        pattern = rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])"
        if re.search(pattern, text):
            hits.append(keyword)
    return hits


def _read_lightweight_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".txt", ".csv"):
        try:
            return path.read_text(encoding="utf-8", errors="ignore")[:20000]
        except OSError:
            return ""
    if suffix == ".pdf":
        return _read_pdf_text(path)
    if suffix in IMAGE_EXTENSIONS:
        return ""
    return ""


def _read_pdf_text(path: Path) -> str:
    pypdf_text = _read_pdf_with_pypdf(path)
    if _has_meaningful_text(pypdf_text):
        return pypdf_text[:30000]

    pdftotext_text = _read_pdf_with_pdftotext(path)
    if _has_meaningful_text(pdftotext_text):
        return pdftotext_text[:30000]

    # Letzter Strohhalm: leerer pypdf-Text ist immer noch besser als nichts.
    return (pypdf_text or pdftotext_text)[:30000]


def _has_meaningful_text(text: str) -> bool:
    # Bild-PDFs liefern oft nur Whitespace oder einzelne Steuerzeichen.
    if not text or len(re.sub(r"\s+", "", text)) < 20:
        return False
    normalized = _normalize_text(text)
    business_words = (
        "rechnung",
        "invoice",
        "gesamt",
        "betrag",
        "datum",
        "lieferung",
        "kund",
        "ust",
        "mwst",
        "eur",
        "gmbh",
        "amazon",
        "porsche",
        "reparatur",
        "wartung",
    )
    if any(word in normalized for word in business_words):
        return True

    printable = sum(1 for char in text if char in string.printable or char in "äöüÄÖÜß€éèàáóíúÉ")
    non_space = len(re.sub(r"\s+", "", text))
    return non_space > 0 and printable / max(len(text), 1) >= 0.75


def _read_pdf_with_pypdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""

    try:
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages[:5])
    except Exception as exc:
        logging.info("PDF-Text konnte nicht mit pypdf gelesen werden: %s (%s)", path, exc)
        return ""


def _read_pdf_with_pdftotext(path: Path) -> str:
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", "-f", "1", "-l", "5", str(path), "-"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def _find_best_date(path: Path, text: str) -> date:
    explicit = _find_date(text)
    period = _find_year_month_period(path, text)
    if period and explicit and explicit.year != period.year:
        return period
    if explicit:
        return explicit
    if period:
        return period
    return _file_date(path)


def _find_date(text: str) -> Optional[date]:
    patterns = (
        r"\b(20\d{2})[.\-/ ](0?[1-9]|1[0-2])[.\-/ ](0?[1-9]|[12]\d|3[01])\b",
        r"\b(0?[1-9]|[12]\d|3[01])[.\-/ ](0?[1-9]|1[0-2])[.\-/ ](20\d{2})\b",
        r"\b(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        parts = match.groups()
        try:
            if len(parts[0]) == 4:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
            return date(int(parts[2]), int(parts[1]), int(parts[0]))
        except ValueError:
            continue
    return None


def _find_year_month_period(path: Path, text: str) -> Optional[date]:
    search_text = _normalize_text(" ".join(path.parts[-6:]))
    stem_text = _normalize_text(path.stem)

    match = re.search(r"\b(20\d{2})[ _./-]+(0?[1-9]|1[0-2])\b", search_text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), 1)

    match = re.search(r"\b(0?[1-9]|1[0-2])[ _./-]+(20\d{2})\b", search_text)
    if match:
        return date(int(match.group(2)), int(match.group(1)), 1)

    year_match = re.search(r"\b(20\d{2})\b", search_text)
    year = int(year_match.group(1)) if year_match else None
    if not year:
        return None

    for word, month in MONTH_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", search_text):
            return date(year, month, 1)

    trailing_month = re.search(r"(?:^|[ _-])(0?[1-9]|1[0-2])(?:$|[ _-])", stem_text)
    if trailing_month:
        return date(year, int(trailing_month.group(1)), 1)

    return None


def _file_date(path: Path) -> date:
    return datetime.fromtimestamp(path.stat().st_mtime).date()


def _find_amount(text: str) -> tuple[Optional[float], str]:
    pattern = r"((?:\d{1,3}(?:[. ]\d{3})+|\d{1,6})(?:[.,]\d{2}))\s?(eur|euro|€|usd|chf)?"
    currency_map = {"€": "EUR", "euro": "EUR", "eur": "EUR", "usd": "USD", "chf": "CHF"}

    porsche_amount = _find_porsche_gross_amount(text)
    if porsche_amount is not None:
        return porsche_amount, "EUR"

    # Bevorzugt eindeutige Brutto-/Zahlbetrag-Signale.
    priority_keywords = (
        "zahlbetrag",
        "endbetrag",
        "gesamtpreis",
        "zu zahlen",
        "kartenzahlung",
        "total",
        "gesamtsumme",
        "gesamtbetrag",
        "brutto",
    )
    for keyword in priority_keywords:
        for match in re.finditer(rf"(?<![a-z0-9]){keyword}(?![a-z0-9])[^\n]{{0,40}}?" + pattern, text, flags=re.IGNORECASE):
            if _looks_like_tax_context(text, match):
                continue
            amount = _parse_decimal(match.group(1))
            currency = currency_map.get((match.group(2) or "").lower(), "EUR")
            return amount, currency

    # Fallback: größter Betrag mit Currency-Hinweis, sonst größter Betrag.
    matches = list(re.finditer(r"\b" + pattern + r"\b", text, flags=re.IGNORECASE))
    if not matches:
        return None, "EUR"

    candidates: list[tuple[float, str]] = []
    for match in matches:
        if _looks_like_time_or_date_amount(text, match):
            continue
        try:
            value = _parse_decimal(match.group(1))
        except ValueError:
            continue
        candidates.append((value, (match.group(2) or "").lower()))

    if not candidates:
        return None, "EUR"

    with_currency = [c for c in candidates if c[1]]
    pool = with_currency or candidates
    amount, raw_currency = max(pool, key=lambda c: c[0])
    return amount, currency_map.get(raw_currency, "EUR")


def _looks_like_time_or_date_amount(text: str, match: re.Match) -> bool:
    start, end = match.span(1)
    before = text[max(0, start - 12):start]
    after = text[end:end + 12]
    value = match.group(1)
    if re.search(r"(?:^|\s)(?:um|at)\s*$", before):
        return True
    if re.match(r"^\s*(?:uhr|h)\b", after):
        return True
    if re.match(r"^\d{1,2}[.,]\d{2}$", value):
        hour = int(value[: value.index(",") if "," in value else value.index(".")])
        if 0 <= hour <= 23 and re.search(r"(?:^|\s)(?:um|at)\s*$", before):
            return True
    if re.search(r"\b20\d{2}[ ._/-]?$", before) or re.match(r"^[ ._/-]?\d{2}\b", after):
        return True
    return False


def _looks_like_tax_context(text: str, match: re.Match) -> bool:
    context = text[max(0, match.start() - 25):match.end() + 25]
    return bool(re.search(r"\b(?:ust|mwst|netto|ohne\s+ust)\b", context))


def _find_porsche_gross_amount(text: str) -> Optional[float]:
    normalized = _normalize_text(text)
    if "porsche" not in normalized or "zwischensumme" not in normalized:
        return None

    net_amounts = []
    for match in re.finditer(r"zwischensumme\s+((?:\d{1,3}(?:[. ]\d{3})+|\d{1,6})(?:[.,]\d{2}))", text, flags=re.IGNORECASE):
        try:
            net_amounts.append(_parse_decimal(match.group(1)))
        except ValueError:
            continue

    if not net_amounts:
        return None
    return round(max(net_amounts) * 1.19 + 1e-9, 2)


def _parse_decimal(value: str) -> float:
    if "," in value:
        return float(value.replace(".", "").replace(",", "."))
    return float(value)


def _find_invoice_number(text: str) -> str:
    patterns = (
        r"\b(rg[ .:#-]*\d[a-z0-9_.-]*)\b",
        r"\b(?:rechnungsnr|rechnungsnummer|invoice no|invoice nr|nr\.|no\.)[ .:#-]*([a-z0-9][a-z0-9_.-]{3,})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return re.sub(r"\s+", "", match.group(1).strip("._-"))
    return ""


def _find_vendor(stem: str, invoice_date: date, vendor_hits: Optional[list] = None) -> str:
    # Wenn ein bekannter Anbieter im Dateinamen/Text gefunden wurde, diesen bevorzugen.
    if vendor_hits:
        # Längster Treffer = spezifischster (z.B. "autoversicherung" vor "auto").
        best = max(vendor_hits, key=len)
        return best.title()

    cleaned = stem.lower().replace("_", " ").replace("-", " ")
    cleaned = re.sub(r"\b20\d{2}[. /-]?(?:0?[1-9]|1[0-2])[. /-]?(?:0?[1-9]|[12]\d|3[01])\b", " ", cleaned)
    cleaned = re.sub(r"\b(?:0?[1-9]|[12]\d|3[01])[. /-](?:0?[1-9]|1[0-2])[. /-]20\d{2}\b", " ", cleaned)
    cleaned = re.sub(r"\b(?:rechnung|invoice|receipt|quittung|beleg|abrechnung|rg|nr)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\brg[ .:#-]*\d[a-z0-9_.-]*\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:eur|euro|usd|chf)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+[.,]?\d*\b", " ", cleaned)
    tokens = [token for token in re.split(r"[\s._-]+", cleaned) if token]
    vendor = " ".join(tokens[:4]).strip()
    if vendor:
        return vendor.title()
    return f"Unbekannt {invoice_date.year}"


def _find_category(vendor_hits: Optional[list], default_category: str) -> str:
    if not vendor_hits:
        return default_category
    for vendor in sorted(vendor_hits, key=len, reverse=True):
        category = KNOWN_VENDOR_CATEGORIES.get(vendor)
        if category:
            return category
    return default_category
