import logging
import time
from dataclasses import dataclass
from pathlib import Path

from core.ha_client import HomeAssistantClient
from core.invoice_archiver import archive_invoice, copy_to_review
from core.invoice_catalog import InvoiceCatalog
from core.invoice_email import EmailConfig, extract_attachments_from_eml, fetch_imap_attachments
from core.invoice_extractor import extract_metadata, file_sha256
from core.invoice_portals import PortalConfig, fetch_portal_documents


SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".txt", ".csv", ".eml"}


@dataclass
class InvoiceAgentConfig:
    inbox_dir: Path
    archive_dir: Path
    review_dir: Path
    database_path: Path
    email_attachment_dir: Path
    poll_interval_seconds: int
    default_category: str = "Unsortiert"
    confidence_threshold: float = 0.5
    reprocess_existing: bool = False
    email: EmailConfig = None
    portals: PortalConfig = None
    home_assistant_notifications: "HomeAssistantNotificationConfig" = None


@dataclass
class HomeAssistantNotificationConfig:
    enabled: bool = False
    only_on_changes: bool = True
    title: str = "Rechnungs-Agent"
    notification_id: str = "invoice_agent"


@dataclass
class ScanResult:
    scanned: int = 0
    archived: int = 0
    review: int = 0
    duplicates: int = 0
    skipped: int = 0
    portal_login_required: list[str] = None

    def __post_init__(self):
        if self.portal_login_required is None:
            self.portal_login_required = []


def scan_once(config: InvoiceAgentConfig) -> ScanResult:
    _ensure_dirs(config)
    catalog = InvoiceCatalog(config.database_path)
    result = ScanResult()

    try:
        if config.portals and config.portals.enabled:
            portal_results = fetch_portal_documents(config.portals)
            for portal_result in portal_results:
                logging.info("Portal Scan: %s", portal_result)
                if portal_result.needs_login:
                    result.portal_login_required.append(portal_result.provider)

        if config.email and config.email.enabled:
            try:
                email_result = fetch_imap_attachments(
                    config=config.email,
                    output_dir=config.email_attachment_dir,
                    is_processed=catalog.has_email_message,
                    mark_processed=catalog.record_email_message,
                )
                logging.info("E-Mail Scan: %s", email_result)
            except Exception as exc:
                logging.warning("E-Mail Scan fehlgeschlagen, lokaler Scan laeuft weiter: %s", exc)

        for path in _iter_input_files(config):
            result.scanned += 1
            file_hash = file_sha256(path)
            if catalog.has_hash(file_hash) and not config.reprocess_existing:
                result.duplicates += 1
                logging.info("Duplikat uebersprungen: %s", path)
                continue

            metadata = extract_metadata(path, default_category=config.default_category)
            if metadata.is_invoice and metadata.confidence >= config.confidence_threshold:
                archive_path = archive_invoice(path, metadata, config.archive_dir)
                catalog.upsert(metadata, archive_path, "archived")
                result.archived += 1
                logging.info("Rechnung archiviert: %s -> %s", path, archive_path)
            else:
                review_path = copy_to_review(path, metadata, config.review_dir)
                catalog.upsert(metadata, review_path, "review")
                result.review += 1
                logging.info("Zur Pruefung abgelegt: %s -> %s", path, review_path)

        written_indexes = catalog.export_monthly_indexes(config.archive_dir)
        for index_path in written_indexes:
            logging.info("Monatsindex geschrieben: %s", index_path)
    finally:
        catalog.close()

    _notify_home_assistant(config, result)
    _notify_portal_logins(config, result)
    return result


def watch(config: InvoiceAgentConfig):
    logging.info("Invoice-Agent beobachtet %s alle %s Sekunden", config.inbox_dir, config.poll_interval_seconds)
    while True:
        result = scan_once(config)
        logging.info("Scan fertig: %s", result)
        time.sleep(config.poll_interval_seconds)


def _ensure_dirs(config: InvoiceAgentConfig) -> None:
    for path in (
        config.inbox_dir,
        config.archive_dir,
        config.review_dir,
        config.database_path.parent,
        config.email_attachment_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _iter_input_files(config: InvoiceAgentConfig):
    for root in (config.inbox_dir, config.email_attachment_dir):
        yield from _iter_files(root)
    if config.portals:
        for provider in config.portals.providers:
            if provider.download_dir:
                yield from _iter_files(provider.download_dir)


def _iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            logging.info("Nicht unterstuetzte Datei uebersprungen: %s", path)
            continue
        if path.suffix.lower() == ".eml":
            yield from extract_attachments_from_eml(path, config.email_attachment_dir)
            continue
        yield path


def _notify_home_assistant(config: InvoiceAgentConfig, result: ScanResult) -> None:
    notify_config = config.home_assistant_notifications
    if not notify_config or not notify_config.enabled:
        return
    if notify_config.only_on_changes and result.archived == 0 and result.review == 0:
        return

    message = (
        f"Scan abgeschlossen.\n\n"
        f"Archiviert: {result.archived}\n"
        f"Zur Pruefung: {result.review}\n"
        f"Duplikate: {result.duplicates}\n"
        f"Gescannt: {result.scanned}"
    )

    try:
        ha = HomeAssistantClient()
        ha.persistent_notification(
            title=notify_config.title,
            message=message,
            notification_id=notify_config.notification_id,
        )
    except Exception as exc:
        logging.warning("Home-Assistant-Benachrichtigung fehlgeschlagen: %s", exc)


def _notify_portal_logins(config: InvoiceAgentConfig, result: ScanResult) -> None:
    notify_config = config.home_assistant_notifications
    if not notify_config or not notify_config.enabled or not result.portal_login_required:
        return

    for provider in result.portal_login_required:
        if provider == "huk24":
            message = (
                "HUK24 verlangt eine neue Anmeldung.\n\n"
                "Bitte auf dem Mac oder Agent-Server ausfuehren:\n\n"
                "`../venv/bin/python agents/invoices.py --portal-login huk24`\n\n"
                "Danach bei HUK24 einloggen, ggf. 2FA bestaetigen, bis ins Postfach navigieren "
                "und im Terminal Enter druecken."
            )
            title = "HUK24 Login erforderlich"
            notification_id = "invoice_agent_huk24_login"
        else:
            message = f"{provider} verlangt eine neue Anmeldung."
            title = "Portal Login erforderlich"
            notification_id = f"invoice_agent_{provider}_login"

        try:
            ha = HomeAssistantClient()
            ha.persistent_notification(
                title=title,
                message=message,
                notification_id=notification_id,
            )
        except Exception as exc:
            logging.warning("Home-Assistant-Portal-Benachrichtigung fehlgeschlagen: %s", exc)
