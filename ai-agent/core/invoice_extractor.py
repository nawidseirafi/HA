import hashlib
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp")

# OCR per Default aktiv, kann ueber INVOICE_OCR_DISABLE=1 abgeschaltet werden.
_OCR_DISABLED = os.getenv("INVOICE_OCR_DISABLE", "").lower() in ("1", "true", "yes")
_OCR_LANG = os.getenv("INVOICE_OCR_LANG", "deu+eng")
_OCR_MAX_PAGES = int(os.getenv("INVOICE_OCR_MAX_PAGES", "5"))
_OCR_MAX_BYTES = int(os.getenv("INVOICE_OCR_MAX_BYTES", str(40 * 1024 * 1024)))  # 40 MB


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
    "apotheke",
    "auto",
    "autoversicherung",
    "carwash",
    "congstar",
    "gebäudeversicherung",
    "gebaudeversicherung",
    "grundbesitz",
    "hausrat",
    "hotel",
    "huk24",
    "iphone",
    "kfz",
    "lkh",
    "restaurant",
    "rechtschutz",
    "rechtsschutz",
    "strato",
    "strom",
    "tankbeleg",
    "tankbelege",
    "telekom",
    "vodafone",
    "wasser",
    "zahn",
    "zahnarzt",
)

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
    path_text = _normalize_text(" ".join(path.parts[-5:]))
    body_text = _read_lightweight_text(path)
    combined = f"{path_text} {filename_text} {_normalize_text(body_text)}".strip()

    keyword_hits = [keyword for keyword in INVOICE_KEYWORDS if keyword in combined]
    vendor_hits = [vendor for vendor in KNOWN_INVOICE_VENDORS if vendor in combined]
    review_hits = [keyword for keyword in REVIEW_KEYWORDS if keyword in combined]
    invoice_date = _find_best_date(path, combined)
    amount, currency = _find_amount(combined)
    invoice_number = _find_invoice_number(combined)
    vendor = _find_vendor(path.stem, invoice_date, vendor_hits)

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
        category=default_category,
        reason="; ".join(reasons) if reasons else "no invoice signals found",
    )


def _normalize_text(value: str) -> str:
    return value.lower().replace("_", " ").replace("-", " ")


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
        return _read_image_with_ocr(path)[:30000]
    return ""


def _read_pdf_text(path: Path) -> str:
    pypdf_text = _read_pdf_with_pypdf(path)
    if _has_meaningful_text(pypdf_text):
        return pypdf_text[:30000]

    pdftotext_text = _read_pdf_with_pdftotext(path)
    if _has_meaningful_text(pdftotext_text):
        return pdftotext_text[:30000]

    ocr_text = _read_pdf_with_ocr(path)
    if ocr_text:
        return ocr_text[:30000]

    # Letzter Strohhalm: leerer pypdf-Text ist immer noch besser als nichts.
    return (pypdf_text or pdftotext_text)[:30000]


def _has_meaningful_text(text: str) -> bool:
    # Bild-PDFs liefern oft nur Whitespace oder einzelne Steuerzeichen.
    return bool(text and len(re.sub(r"\s+", "", text)) >= 20)


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


def _read_image_with_ocr(path: Path) -> str:
    if _OCR_DISABLED:
        return ""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logging.debug("OCR uebersprungen (pytesseract/Pillow nicht installiert): %s", path)
        return ""

    try:
        with Image.open(path) as img:
            return pytesseract.image_to_string(img, lang=_OCR_LANG)
    except Exception as exc:
        logging.info("OCR fuer Bild fehlgeschlagen: %s (%s)", path, exc)
        return ""


def _read_pdf_with_ocr(path: Path) -> str:
    if _OCR_DISABLED:
        return ""
    try:
        if path.stat().st_size > _OCR_MAX_BYTES:
            logging.info("OCR uebersprungen, PDF zu gross (%s Bytes): %s", path.stat().st_size, path)
            return ""
    except OSError:
        return ""

    try:
        import pytesseract
    except ImportError:
        logging.debug("OCR uebersprungen (pytesseract nicht installiert): %s", path)
        return ""

    images = _pdf_to_images(path)
    if not images:
        return ""

    parts = []
    for image in images:
        try:
            parts.append(pytesseract.image_to_string(image, lang=_OCR_LANG))
        except Exception as exc:
            logging.info("OCR-Seite fehlgeschlagen: %s (%s)", path, exc)
        finally:
            try:
                image.close()
            except Exception:
                pass
    return "\n".join(parts)


def _pdf_to_images(path: Path):
    # Bevorzugt pdf2image (Poppler), Fallback auf PyMuPDF (fitz).
    try:
        from pdf2image import convert_from_path
        try:
            return convert_from_path(str(path), dpi=200, first_page=1, last_page=_OCR_MAX_PAGES)
        except Exception as exc:
            logging.info("pdf2image fehlgeschlagen, versuche PyMuPDF: %s (%s)", path, exc)
    except ImportError:
        pass

    try:
        import fitz  # type: ignore
        from PIL import Image
        import io
    except ImportError:
        if not shutil.which("pdftoppm"):
            logging.info("OCR nicht moeglich: weder pdf2image+Poppler noch PyMuPDF verfuegbar (%s)", path)
        return []

    images = []
    try:
        with fitz.open(str(path)) as doc:
            for page_index in range(min(len(doc), _OCR_MAX_PAGES)):
                pix = doc[page_index].get_pixmap(dpi=200)
                images.append(Image.open(io.BytesIO(pix.tobytes("png"))))
    except Exception as exc:
        logging.info("PyMuPDF-Render fehlgeschlagen: %s (%s)", path, exc)
        return []
    return images


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
    pattern = r"(\d{1,6}(?:[.,]\d{2}))\s?(eur|euro|€|usd|chf)?"
    currency_map = {"€": "EUR", "euro": "EUR", "eur": "EUR", "usd": "USD", "chf": "CHF"}

    # Bevorzugt Beträge in der Nähe von Schlüsselwörtern wie "summe", "gesamt", "brutto", "total".
    priority_keywords = ("gesamtsumme", "gesamtbetrag", "summe", "gesamt", "brutto", "total", "zahlbetrag", "endbetrag")
    for keyword in priority_keywords:
        for match in re.finditer(rf"{keyword}[^\n]{{0,40}}?" + pattern, text, flags=re.IGNORECASE):
            amount = _parse_decimal(match.group(1))
            currency = currency_map.get((match.group(2) or "").lower(), "EUR")
            return amount, currency

    # Fallback: größter Betrag mit Currency-Hinweis, sonst größter Betrag.
    matches = list(re.finditer(r"\b" + pattern + r"\b", text, flags=re.IGNORECASE))
    if not matches:
        return None, "EUR"

    candidates: list[tuple[float, str]] = []
    for match in matches:
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
