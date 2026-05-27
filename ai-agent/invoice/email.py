import logging
import imaplib
import re
import shlex
from email import policy
from email.parser import BytesParser
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass


DEFAULT_ATTACHMENT_EXTENSIONS = (".pdf",)
CONTENT_TYPE_EXTENSIONS = {
    "application/pdf": ".pdf"
}
AUTO_ATTACHMENT_CONTENT_TYPES = {"application/pdf"}
IMAP_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass
class EmailConfig:
    enabled: bool = False
    host: str = ""
    port: int = 993
    username: str = ""
    password: str = ""
    mailbox: str = "INBOX"
    search: str = "UNSEEN"
    mark_seen: bool = False
    max_messages: int = 25
    lookback_days: int = 7
    attachment_extensions: tuple[str, ...] = DEFAULT_ATTACHMENT_EXTENSIONS


@dataclass
class EmailFetchResult:
    messages_seen: int = 0
    messages_new: int = 0
    attachments_saved: int = 0
    files: list[Path] = None
    message_keys_by_file: dict[str, str] = None

    def __post_init__(self):
        if self.files is None:
            self.files = []
        if self.message_keys_by_file is None:
            self.message_keys_by_file = {}


def fetch_imap_attachments(
    config: EmailConfig,
    output_dir: Path,
    is_processed,
    mark_processed,
) -> EmailFetchResult:
    result = EmailFetchResult()
    if not config.enabled:
        return result
    if not config.host or not config.username or not config.password:
        logging.warning("E-Mail ist aktiviert, aber host/username/password fehlen.")
        return result

    output_dir.mkdir(parents=True, exist_ok=True)
    with imaplib.IMAP4_SSL(config.host, config.port) as mailbox:
        mailbox.login(config.username, config.password)
        mailbox.select(config.mailbox)

        search_criteria = _search_criteria(config)
        status, data = mailbox.uid("search", None, *search_criteria)
        if status != "OK":
            logging.warning("IMAP search fehlgeschlagen: %s %s", status, data)
            return result

        uids = data[0].split()
        result.messages_seen = len(uids)
        import_key = _import_key(config)
        selected_uids = uids[-config.max_messages:]
        first_uid = selected_uids[0].decode("ascii", errors="ignore") if selected_uids else "-"
        last_uid = selected_uids[-1].decode("ascii", errors="ignore") if selected_uids else "-"
        logging.info(
            "E-Mail Suche: %s Treffer fuer %s, pruefe letzte %s UIDs (%s bis %s).",
            len(uids),
            " ".join(search_criteria),
            len(selected_uids),
            first_uid,
            last_uid,
        )
        for uid_bytes in selected_uids:
            uid = uid_bytes.decode("ascii", errors="ignore")
            message_key = f"{config.host}:{config.mailbox}:{uid}:{import_key}"
            if is_processed(message_key):
                continue

            status, message_data = mailbox.uid("fetch", uid, "(RFC822)")
            if status != "OK":
                logging.warning("IMAP fetch fehlgeschlagen fuer UID %s: %s", uid, status)
                continue

            raw_message = _message_bytes(message_data)
            if not raw_message:
                continue

            message = BytesParser(policy=policy.default).parsebytes(raw_message)
            subject = str(message.get("subject", "")).strip()
            sender = str(message.get("from", "")).strip()
            saved = _extract_attachments_from_message(
                message=message,
                output_dir=output_dir,
                attachment_extensions=config.attachment_extensions,
                prefix=f"mail_{uid}_",
            )
            result.messages_new += 1
            result.attachments_saved += len(saved)
            result.files.extend(saved)
            if not saved:
                mark_processed(message_key)
            else:
                for path in saved:
                    result.message_keys_by_file[str(path.resolve())] = message_key

            if config.mark_seen:
                mailbox.uid("store", uid, "+FLAGS", "(\\Seen)")

            logging.info(
                "E-Mail UID %s verarbeitet, %s Anhaenge gespeichert. Von=%s Betreff=%s",
                uid,
                len(saved),
                sender or "-",
                subject or "-",
            )
            if not saved:
                logging.info(
                    "E-Mail UID %s hatte keine passenden Anhaenge. Erlaubte Endungen=%s",
                    uid,
                    ", ".join(config.attachment_extensions),
                )

    return result


def extract_attachments_from_eml(eml_path: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with eml_path.open("rb") as f:
        message = BytesParser(policy=policy.default).parse(f)

    extracted = _extract_attachments_from_message(
        message=message,
        output_dir=output_dir,
        attachment_extensions=DEFAULT_ATTACHMENT_EXTENSIONS,
        prefix="",
    )
    for target in extracted:
        logging.info("E-Mail-Anhang extrahiert: %s -> %s", eml_path, target)
    return extracted


def _extract_attachments_from_message(message, output_dir: Path, attachment_extensions: tuple[str, ...], prefix: str) -> list[Path]:
    extracted = []
    for index, part in enumerate(message.walk(), start=1):
        if part.is_multipart():
            continue
        filename = part.get_filename()
        content_type = part.get_content_type().lower()
        disposition = (part.get_content_disposition() or "").lower()
        suffix = Path(filename or "").suffix.lower()
        inferred_suffix = CONTENT_TYPE_EXTENSIONS.get(content_type, "")
        is_named_attachment = bool(filename)
        is_attachment_part = disposition in {"attachment", "inline"}
        is_auto_attachment_content = content_type in AUTO_ATTACHMENT_CONTENT_TYPES and inferred_suffix in attachment_extensions

        if not is_named_attachment and not is_attachment_part and not is_auto_attachment_content:
            continue

        if not suffix and inferred_suffix:
            suffix = inferred_suffix

        if suffix not in attachment_extensions:
            label = filename or f"part-{index} ({content_type})"
            logging.info("E-Mail-Anhang mit nicht unterstuetzter Endung uebersprungen: %s", label)
            continue

        safe_name = _safe_attachment_filename(filename or f"attachment_{index}{suffix}", suffix)
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        target = _unique_path(output_dir / f"{prefix}{safe_name}")
        target.write_bytes(payload)
        extracted.append(target)
    return extracted


def _import_key(config: EmailConfig) -> str:
    extensions = ",".join(sorted(ext.lower() for ext in config.attachment_extensions))
    return f"v3:{extensions}"


def _search_criteria(config: EmailConfig) -> list[str]:
    criteria = shlex.split(config.search or "UNSEEN")
    if not criteria:
        criteria = ["UNSEEN"]
    if config.lookback_days > 0 and not any(item.upper() in {"SINCE", "SENTSINCE"} for item in criteria):
        since = datetime.now() - timedelta(days=config.lookback_days)
        criteria.extend(["SINCE", _imap_date(since)])
    return criteria


def _imap_date(value: datetime) -> str:
    return f"{value.day:02d}-{IMAP_MONTHS[value.month - 1]}-{value.year}"


def _safe_attachment_filename(filename: str, suffix: str) -> str:
    path_name = Path(filename).name.strip() or f"attachment{suffix}"
    stem = Path(path_name).stem.strip()
    current_suffix = Path(path_name).suffix.lower() or suffix
    safe_stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" ._-") or "attachment"
    return f"{safe_stem}{current_suffix}"


def _message_bytes(message_data) -> bytes:
    for item in message_data:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
            return item[1]
    return b""


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for counter in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Kein freier Dateiname gefunden fuer {path}")
