import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.services.core.ha_client import HomeAssistantClient
from .ai_extractor import refine_metadata_with_ai
from .archiver import archive_invoice, copy_to_review
from .catalog import InvoiceCatalog
from .categories import apply_category_rules
from .cleanup_archive import cleanup_archive
from .email import EmailConfig, extract_attachments_from_eml, fetch_imap_attachments
from .extractor import extract_metadata, file_sha256
from .portals import PortalConfig, fetch_portal_documents


SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".txt", ".csv", ".eml"}
AI_EXTRACTABLE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}


@dataclass
class InvoiceAgentConfig:
    inbox_dir: Path
    archive_dir: Path
    review_dir: Path
    database_path: Path
    email_attachment_dir: Path
    archive_cleanup_backup_dir: Path
    poll_interval_seconds: int
    default_category: str = "Unsortiert"
    category_rules: dict[str, str] = None
    confidence_threshold: float = 0.5
    require_amount_for_archive: bool = True
    reprocess_existing: bool = False
    email: EmailConfig = None
    portals: PortalConfig = None
    home_assistant_notifications: "HomeAssistantNotificationConfig" = None
    ai_extraction: "AIExtractionConfig" = None
    archive_cleanup: "ArchiveCleanupConfig" = None
    llm_config: Optional[dict] = None


@dataclass
class HomeAssistantNotificationConfig:
    enabled: bool = False
    only_on_changes: bool = True
    title: str = "Rechnungs-Agent"
    notification_id: str = "invoice_agent"
    notify_service: str = ""
    persistent: bool = True


@dataclass
class AIExtractionConfig:
    enabled: bool = False
    min_confidence: float = 0.8
    max_file_bytes: int = 10 * 1024 * 1024
    always_for_documents: bool = True


@dataclass
class ArchiveCleanupConfig:
    enabled: bool = False
    apply: bool = False


@dataclass
class ScanResult:
    scanned: int = 0
    archived: int = 0
    review: int = 0
    duplicates: int = 0
    skipped: int = 0
    cleanup_unreferenced: int = 0
    cleanup_missing: int = 0
    cleanup_moved: int = 0
    portal_login_required: list[str] = None

    def __post_init__(self):
        if self.portal_login_required is None:
            self.portal_login_required = []


def scan_once(config: InvoiceAgentConfig) -> ScanResult:
    _ensure_dirs(config)
    catalog = InvoiceCatalog(config.database_path)
    result = ScanResult()
    llm_client = None
    email_message_keys_by_file = {}

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
                email_message_keys_by_file.update(email_result.message_keys_by_file)
                logging.info("E-Mail Scan: %s", email_result)
            except Exception as exc:
                logging.warning("E-Mail Scan fehlgeschlagen, lokaler Scan laeuft weiter: %s", exc)

        for path in _iter_input_files(config):
            result.scanned += 1
            file_hash = file_sha256(path)
            if catalog.has_hash(file_hash) and not config.reprocess_existing:
                result.duplicates += 1
                logging.info("Duplikat uebersprungen: %s", path)
                _mark_email_file_processed(path, email_message_keys_by_file, catalog)
                _discard_input_file(path, config)
                continue

            metadata = extract_metadata(path, default_category=config.default_category)
            if _should_use_ai_extraction(config, metadata, path):
                if llm_client is None:
                    llm_client = _create_llm_client(config)
                if llm_client is not None:
                    try:
                        metadata = refine_metadata_with_ai(
                            path=path,
                            metadata=metadata,
                            llm_client=llm_client,
                            default_category=config.default_category,
                        )
                    except Exception as exc:
                        logging.warning("KI-Belegextraktion fehlgeschlagen, lokale Metadaten werden genutzt: %s", exc)
            metadata = apply_category_rules(metadata, config.category_rules, config.default_category)
            if catalog.has_metadata_duplicate(metadata) and not config.reprocess_existing:
                result.duplicates += 1
                logging.info(
                    "Metadaten-Duplikat uebersprungen: %s (%s, %s, %s)",
                    path,
                    metadata.vendor,
                    metadata.invoice_date,
                    metadata.amount,
                )
                _mark_email_file_processed(path, email_message_keys_by_file, catalog)
                _discard_input_file(path, config)
                continue
            if _should_archive(config, metadata):
                archive_path = archive_invoice(path, metadata, config.archive_dir)
                catalog.upsert(metadata, archive_path, "archived")
                _mark_email_file_processed(path, email_message_keys_by_file, catalog)
                result.archived += 1
                logging.info("Rechnung archiviert: %s -> %s", path, archive_path)
            else:
                review_path = copy_to_review(path, metadata, config.review_dir)
                catalog.upsert(metadata, review_path, "review")
                _mark_email_file_processed(path, email_message_keys_by_file, catalog)
                result.review += 1
                logging.info("Zur Pruefung abgelegt: %s -> %s", path, review_path)

        written_indexes = catalog.export_monthly_indexes(config.archive_dir)
        for index_path in written_indexes:
            logging.info("Monatsindex geschrieben: %s", index_path)

        cleanup_result = _cleanup_archive(config)
        if cleanup_result:
            result.cleanup_unreferenced = cleanup_result.unreferenced
            result.cleanup_missing = cleanup_result.missing
            result.cleanup_moved = cleanup_result.moved
    finally:
        catalog.close()

    _notify_home_assistant(config, result)
    _notify_portal_logins(config, result)
    return result


def _should_archive(config: InvoiceAgentConfig, metadata) -> bool:
    if not metadata.is_invoice or metadata.confidence < config.confidence_threshold:
        return False
    if config.require_amount_for_archive and metadata.amount is None:
        return False
    return True


def _should_use_ai_extraction(config: InvoiceAgentConfig, metadata, path: Path) -> bool:
    ai_config = config.ai_extraction
    if not ai_config or not ai_config.enabled:
        return False
    if path.suffix.lower() not in AI_EXTRACTABLE_EXTENSIONS:
        return False
    try:
        if path.stat().st_size > ai_config.max_file_bytes:
            logging.info("KI-Belegextraktion uebersprungen, Datei zu gross: %s", path)
            return False
    except OSError:
        return False
    if ai_config.always_for_documents:
        return True
    return (
        metadata.confidence < ai_config.min_confidence
        or metadata.amount is None
        or "no_readable_text" in metadata.reason
    )


def _create_llm_client(config: InvoiceAgentConfig):
    if not config.llm_config:
        logging.info("KI-Belegextraktion deaktiviert: keine llm-Konfiguration vorhanden.")
        return None
    try:
        from backend.services.llm.factory import create_llm_client
        return create_llm_client({"llm": config.llm_config})
    except Exception as exc:
        logging.warning("LLM-Client konnte nicht erstellt werden: %s", exc)
        return None


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
        config.archive_cleanup_backup_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _cleanup_archive(config: InvoiceAgentConfig):
    cleanup_config = config.archive_cleanup
    if not cleanup_config or not cleanup_config.enabled:
        return None
    try:
        result = cleanup_archive(
            database_path=config.database_path,
            archive_dir=config.archive_dir,
            backup_dir=config.archive_cleanup_backup_dir,
            apply=cleanup_config.apply,
        )
    except Exception as exc:
        logging.warning("Archiv-Cleanup fehlgeschlagen: %s", exc)
        return None
    logging.info(
        "Archiv-Cleanup: archive_files=%s db_references=%s unreferenced=%s missing=%s moved=%s backup=%s",
        result.archive_files,
        result.db_references,
        result.unreferenced,
        result.missing,
        result.moved,
        result.backup_dir or "-",
    )
    return result


def _iter_input_files(config: InvoiceAgentConfig):
    roots = []
    for root in (config.inbox_dir, config.email_attachment_dir):
        if root not in roots:
            roots.append(root)
    if config.portals:
        for provider in config.portals.providers:
            if provider.download_dir and provider.download_dir not in roots:
                roots.append(provider.download_dir)
    for root in roots:
        yield from _iter_files(root, config.email_attachment_dir)


def _iter_files(root: Path, attachment_dir: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            logging.info("Nicht unterstuetzte Datei uebersprungen: %s", path)
            continue
        if path.suffix.lower() == ".eml":
            extracted = extract_attachments_from_eml(path, attachment_dir)
            if extracted:
                try:
                    path.unlink()
                except OSError as exc:
                    logging.warning("Verarbeitete EML konnte nicht entfernt werden: %s (%s)", path, exc)
            yield from extracted
            continue
        yield path


def _discard_input_file(path: Path, config: InvoiceAgentConfig) -> None:
    roots = [config.inbox_dir, config.email_attachment_dir]
    if config.portals:
        roots.extend(provider.download_dir for provider in config.portals.providers if provider.download_dir)
    if not _is_inside_any(path, roots):
        return
    try:
        path.unlink()
        logging.info("Eingangsduplikat entfernt: %s", path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logging.warning("Eingangsduplikat konnte nicht entfernt werden: %s (%s)", path, exc)


def _mark_email_file_processed(path: Path, message_keys_by_file: dict[str, str], catalog: InvoiceCatalog) -> None:
    try:
        message_key = message_keys_by_file.get(str(path.resolve()))
    except OSError:
        message_key = None
    if message_key:
        catalog.record_email_message(message_key)


def _is_inside_any(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except (OSError, ValueError):
            continue
    return False


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
        if notify_config.notify_service:
            ha.notify(
                service=notify_config.notify_service,
                title=notify_config.title,
                message=message,
                data={
                    "tag": notify_config.notification_id,
                    "group": "invoice_agent",
                },
            )
        if notify_config.persistent:
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
                "`../venv/bin/python invoice/invoices.py --portal-login huk24`\n\n"
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
            if notify_config.notify_service:
                ha.notify(
                    service=notify_config.notify_service,
                    title=title,
                    message=message,
                    data={
                        "tag": notification_id,
                        "group": "invoice_agent",
                    },
                )
            if notify_config.persistent:
                ha.persistent_notification(
                    title=title,
                    message=message,
                    notification_id=notification_id,
                )
        except Exception as exc:
            logging.warning("Home-Assistant-Portal-Benachrichtigung fehlgeschlagen: %s", exc)
