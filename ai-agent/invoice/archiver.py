import re
import shutil
import filecmp
from pathlib import Path

from invoice.extractor import InvoiceMetadata


MONTH_NAMES = (
    "01-Januar",
    "02-Februar",
    "03-Maerz",
    "04-April",
    "05-Mai",
    "06-Juni",
    "07-Juli",
    "08-August",
    "09-September",
    "10-Oktober",
    "11-November",
    "12-Dezember",
)


def archive_invoice(source: Path, metadata: InvoiceMetadata, archive_dir: Path) -> Path:
    month_dir = archive_dir / str(metadata.invoice_date.year) / MONTH_NAMES[metadata.invoice_date.month - 1]
    month_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_or_existing_same_file(source, month_dir / _archive_filename(source, metadata))
    return _move_to_target(source, target)


def copy_to_review(source: Path, metadata: InvoiceMetadata, review_dir: Path) -> Path:
    month_dir = review_dir / str(metadata.invoice_date.year) / MONTH_NAMES[metadata.invoice_date.month - 1]
    month_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_or_existing_same_file(source, month_dir / source.name)
    return _move_to_target(source, target)


def month_dir_for(archive_dir: Path, year: int, month: int) -> Path:
    return archive_dir / str(year) / MONTH_NAMES[month - 1]


def _archive_filename(source: Path, metadata: InvoiceMetadata) -> str:
    vendor = _slug(metadata.vendor) or "Unbekannt"
    amount = f"_{metadata.amount:.2f}_{metadata.currency}" if metadata.amount is not None else ""
    number = f"_{_slug(metadata.invoice_number)}" if metadata.invoice_number else ""
    return f"{vendor}_{metadata.invoice_date.isoformat()}{amount}{number}{source.suffix.lower()}"


def _slug(value: str) -> str:
    value = value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    value = re.sub(r"[^A-Za-z0-9]+", "_", value)
    return value.strip("_")[:80]


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for counter in range(2, 1000):
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Kein freier Dateiname gefunden fuer {path}")


def _unique_or_existing_same_file(source: Path, path: Path) -> Path:
    if not path.exists():
        return path
    if _same_file(source, path):
        return path

    stem = path.stem
    suffix = path.suffix
    for counter in range(2, 1000):
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        if _same_file(source, candidate):
            return candidate
    raise RuntimeError(f"Kein freier Dateiname gefunden fuer {path}")


def _move_to_target(source: Path, target: Path) -> Path:
    try:
        if source.resolve() == target.resolve():
            return target
    except OSError:
        pass
    if target.exists() and _same_file(source, target):
        source.unlink()
        return target
    shutil.move(str(source), str(target))
    return target


def _same_file(left: Path, right: Path) -> bool:
    try:
        return left.stat().st_size == right.stat().st_size and filecmp.cmp(left, right, shallow=False)
    except OSError:
        return False
