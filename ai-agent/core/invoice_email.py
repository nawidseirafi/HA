import logging
import imaplib
from email import policy
from email.parser import BytesParser
from pathlib import Path
from dataclasses import dataclass


DEFAULT_ATTACHMENT_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".txt", ".csv")


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
    attachment_extensions: tuple[str, ...] = DEFAULT_ATTACHMENT_EXTENSIONS


@dataclass
class EmailFetchResult:
    messages_seen: int = 0
    messages_new: int = 0
    attachments_saved: int = 0
    files: list[Path] = None

    def __post_init__(self):
        if self.files is None:
            self.files = []


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

        status, data = mailbox.uid("search", None, config.search)
        if status != "OK":
            logging.warning("IMAP search fehlgeschlagen: %s %s", status, data)
            return result

        uids = data[0].split()
        result.messages_seen = len(uids)
        for uid_bytes in uids[-config.max_messages:]:
            uid = uid_bytes.decode("ascii", errors="ignore")
            message_key = f"{config.host}:{config.mailbox}:{uid}"
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
            saved = _extract_attachments_from_message(
                message=message,
                output_dir=output_dir,
                attachment_extensions=config.attachment_extensions,
                prefix=f"mail_{uid}_",
            )
            result.messages_new += 1
            result.attachments_saved += len(saved)
            result.files.extend(saved)
            mark_processed(message_key)

            if config.mark_seen:
                mailbox.uid("store", uid, "+FLAGS", "(\\Seen)")

            logging.info("E-Mail UID %s verarbeitet, %s Anhaenge gespeichert.", uid, len(saved))

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
    for part in message.iter_attachments():
        filename = part.get_filename()
        if not filename:
            continue
        if Path(filename).suffix.lower() not in attachment_extensions:
            logging.info("E-Mail-Anhang mit nicht unterstuetzter Endung uebersprungen: %s", filename)
            continue
        target = _unique_path(output_dir / f"{prefix}{filename}")
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        target.write_bytes(payload)
        extracted.append(target)
    return extracted


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
