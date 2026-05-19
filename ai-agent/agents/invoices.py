import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.invoice_email import EmailConfig
from core.invoice_portals import PortalConfig, PortalProviderConfig, fetch_huk24_documents, login_portal
from core.invoice_scanner import HomeAssistantNotificationConfig, InvoiceAgentConfig, scan_once, watch
from core.tax_export import DEFAULT_CATEGORY_RULES, TaxExportConfig, export_tax_year


def load_raw_config() -> dict:
    load_dotenv(BASE_DIR / ".env")

    with (BASE_DIR / "config.yaml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(raw_config: Optional[dict] = None) -> InvoiceAgentConfig:
    if raw_config is None:
        raw_config = load_raw_config()

    invoice_config = raw_config.get("invoice_agent", {})
    email_config = invoice_config.get("email", {})
    portals_config = invoice_config.get("portals", {})
    ha_notification_config = invoice_config.get("home_assistant_notifications", {})
    data_dir = BASE_DIR / "data" / "invoices"

    return InvoiceAgentConfig(
        inbox_dir=_path(invoice_config.get("inbox_dir", data_dir / "inbox")),
        archive_dir=_path(invoice_config.get("archive_dir", data_dir / "archive")),
        review_dir=_path(invoice_config.get("review_dir", data_dir / "review")),
        database_path=_path(invoice_config.get("database_path", data_dir / "invoices.db")),
        email_attachment_dir=_path(invoice_config.get("email_attachment_dir", data_dir / "extracted_email_attachments")),
        poll_interval_seconds=int(invoice_config.get("poll_interval_seconds", 600)),
        default_category=invoice_config.get("default_category", "Unsortiert"),
        confidence_threshold=float(invoice_config.get("confidence_threshold", 0.5)),
        reprocess_existing=bool(invoice_config.get("reprocess_existing", False)),
        email=_load_email_config(email_config),
        portals=_load_portal_config(portals_config, data_dir),
        home_assistant_notifications=_load_ha_notification_config(ha_notification_config),
    )


def load_tax_config(raw_config: Optional[dict] = None) -> TaxExportConfig:
    if raw_config is None:
        raw_config = load_raw_config()
    invoice_config = raw_config.get("invoice_agent", {})
    tax_config = raw_config.get("tax_export", {})
    data_dir = BASE_DIR / "data" / "invoices"

    rules = dict(DEFAULT_CATEGORY_RULES)
    rules.update(tax_config.get("categories", {}))

    return TaxExportConfig(
        database_path=_path(invoice_config.get("database_path", data_dir / "invoices.db")),
        output_dir=_path(tax_config.get("output_dir", data_dir / "tax")),
        category_rules=rules,
    )


def main():
    raw_config = load_raw_config()
    portal_names = _portal_provider_names(raw_config)

    parser = argparse.ArgumentParser(description="Rechnungen suchen, katalogisieren und monatlich ablegen.")
    parser.add_argument("--once", action="store_true", help="Einmal scannen und beenden.")
    parser.add_argument("--watch", action="store_true", help="Dauerhaft beobachten.")
    parser.add_argument("--reprocess", action="store_true", help="Bereits bekannte Dateien erneut auswerten.")
    parser.add_argument("--portal-login", choices=portal_names or None, help="Interaktiven Portal-Login starten und Session speichern.")
    parser.add_argument("--portal-check", choices=portal_names or None, help="Nur ein Portal pruefen und Downloads speichern.")
    parser.add_argument("--tax-year", type=int, help="Steuer-Export fuer dieses Jahr erzeugen, z.B. 2025.")
    args = parser.parse_args()

    _setup_logging()
    config = load_config(raw_config)
    if args.reprocess:
        config.reprocess_existing = True

    if args.portal_login:
        provider = _find_portal_provider(config.portals, args.portal_login)
        result = login_portal(provider)
        logging.info("Portal-Login fertig: %s", result)
        print(result)
        return

    if args.portal_check:
        provider = _find_portal_provider(config.portals, args.portal_check)
        if provider.name == "huk24":
            result = fetch_huk24_documents(provider)
        else:
            raise ValueError(f"Portal nicht unterstuetzt: {provider.name}")
        logging.info("Portal-Check fertig: %s", result)
        print(result)
        return

    if args.watch:
        watch(config)
        return

    # Standard: scannen, ausser es wurde ausschliesslich --tax-year angefordert.
    if args.once or not args.tax_year:
        result = scan_once(config)
        logging.info("Invoice-Agent fertig: %s", result)
        print(result)

    if args.tax_year:
        tax_result = export_tax_year(load_tax_config(raw_config), args.tax_year)
        logging.info("Tax-Export fertig: %s", tax_result)
        print(tax_result)


def _path(value) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (BASE_DIR / path).resolve()


def _load_email_config(email_config: dict) -> EmailConfig:
    extensions = email_config.get("attachment_extensions")
    if extensions:
        attachment_extensions = tuple(ext.lower() for ext in extensions)
    else:
        attachment_extensions = EmailConfig().attachment_extensions

    return EmailConfig(
        enabled=bool(email_config.get("enabled", False)),
        host=os.getenv(email_config.get("host_env", "INVOICE_EMAIL_HOST"), email_config.get("host", "")),
        port=int(email_config.get("port", 993)),
        username=os.getenv(email_config.get("username_env", "INVOICE_EMAIL_USERNAME"), ""),
        password=os.getenv(email_config.get("password_env", "INVOICE_EMAIL_PASSWORD"), ""),
        mailbox=email_config.get("mailbox", "INBOX"),
        search=email_config.get("search", "UNSEEN"),
        mark_seen=bool(email_config.get("mark_seen", False)),
        max_messages=int(email_config.get("max_messages", 25)),
        attachment_extensions=attachment_extensions,
    )


def _load_portal_config(config: dict, data_dir: Path) -> PortalConfig:
    providers = []
    portal_dir = data_dir / "portal_downloads"
    session_dir = data_dir / "portal_sessions"
    for raw_provider in config.get("providers", []):
        name = raw_provider.get("name", "")
        providers.append(
            PortalProviderConfig(
                name=name,
                enabled=bool(raw_provider.get("enabled", False)),
                url=raw_provider.get("url", ""),
                session_path=_path(raw_provider.get("session_path", session_dir / f"{name}.json")),
                download_dir=_path(raw_provider.get("download_dir", portal_dir / name)),
                headless=bool(raw_provider.get("headless", True)),
                wait_seconds=int(raw_provider.get("wait_seconds", 20)),
                debug_dir=_path(raw_provider.get("debug_dir", data_dir / "portal_debug" / name)),
            )
        )
    return PortalConfig(
        enabled=bool(config.get("enabled", False)),
        providers=providers,
    )


def _find_portal_provider(config: PortalConfig, name: str) -> PortalProviderConfig:
    if not config or not config.providers:
        raise ValueError("Keine Portale konfiguriert.")
    for provider in config.providers:
        if provider.name == name:
            return provider
    raise ValueError(f"Portal nicht konfiguriert: {name}")


def _portal_provider_names(raw_config: dict) -> list[str]:
    portals = (raw_config.get("invoice_agent", {}) or {}).get("portals", {}) or {}
    return [p.get("name", "") for p in portals.get("providers", []) if p.get("name")]


def _load_ha_notification_config(config: dict) -> HomeAssistantNotificationConfig:
    return HomeAssistantNotificationConfig(
        enabled=bool(config.get("enabled", False)),
        only_on_changes=bool(config.get("only_on_changes", True)),
        title=config.get("title", "Rechnungs-Agent"),
        notification_id=config.get("notification_id", "invoice_agent"),
    )


def _setup_logging():
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Verhindert doppelte Handler, falls _setup_logging mehrfach aufgerufen wird.
    if not any(isinstance(h, logging.FileHandler) and getattr(h, "_invoice_agent", False) for h in root.handlers):
        file_handler = logging.FileHandler(log_dir / "agent.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler._invoice_agent = True  # type: ignore[attr-defined]
        root.addHandler(file_handler)

    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in root.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)


if __name__ == "__main__":
    main()
