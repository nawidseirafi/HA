import logging
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PortalProviderConfig:
    name: str
    enabled: bool = False
    url: str = ""
    session_path: Path = None
    download_dir: Path = None
    headless: bool = True
    wait_seconds: int = 45
    debug_dir: Path = None


@dataclass
class PortalConfig:
    enabled: bool = False
    providers: list[PortalProviderConfig] = None

    def __post_init__(self):
        if self.providers is None:
            self.providers = []


@dataclass
class PortalFetchResult:
    provider: str
    downloaded: int = 0
    files: list[Path] = None
    needs_login: bool = False

    def __post_init__(self):
        if self.files is None:
            self.files = []


def fetch_portal_documents(config: PortalConfig) -> list[PortalFetchResult]:
    results = []
    if not config.enabled:
        return results

    for provider in config.providers:
        if not provider.enabled:
            continue
        try:
            if provider.name == "huk24":
                results.append(fetch_huk24_documents(provider))
            else:
                logging.warning("Unbekannter Portal-Provider: %s", provider.name)
        except Exception as exc:
            logging.warning("Portal %s fehlgeschlagen: %s", provider.name, exc)
            results.append(PortalFetchResult(provider=provider.name, needs_login=True))
    return results


def login_portal(provider: PortalProviderConfig) -> PortalFetchResult:
    if provider.name != "huk24":
        raise ValueError(f"Unbekannter Portal-Provider: {provider.name}")
    return fetch_huk24_documents(provider, interactive_login=True)


def fetch_huk24_documents(config: PortalProviderConfig, interactive_login: bool = False) -> PortalFetchResult:
    sync_playwright = _load_playwright()
    config.download_dir.mkdir(parents=True, exist_ok=True)
    config.session_path.parent.mkdir(parents=True, exist_ok=True)
    if config.debug_dir:
        config.debug_dir.mkdir(parents=True, exist_ok=True)

    result = PortalFetchResult(provider=config.name)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=config.headless and not interactive_login)
        context_kwargs = {
            "accept_downloads": True,
            "viewport": {"width": 1440, "height": 1000},
        }
        if config.session_path.exists():
            context_kwargs["storage_state"] = str(config.session_path)

        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.goto(config.url, wait_until="domcontentloaded", timeout=60000)
        logging.info("HUK24 Seite geladen: %s", page.url)
        _accept_cookie_banner(page)

        if interactive_login:
            print("HUK24 Login-Fenster ist offen. Bitte einloggen und bis zum Postfach navigieren.")
            input("Wenn du eingeloggt bist, hier Enter druecken ... ")
            page.goto(config.url, wait_until="domcontentloaded", timeout=60000)
            _accept_cookie_banner(page)
            _wait_for_huk24_app(page, config)
            _save_debug_snapshot(page, config, "huk24_postfach_after_login")
            context.storage_state(path=str(config.session_path))
            browser.close()
            logging.info("HUK24 Session gespeichert: %s", config.session_path)
            return result

        if _looks_like_login(page):
            result.needs_login = True
            logging.info("HUK24 braucht Login. Starte einmal: agents/invoices.py --portal-login huk24")
            browser.close()
            return result

        _wait_for_huk24_app(page, config)
        _accept_cookie_banner(page)
        if _looks_like_login(page):
            result.needs_login = True
            _save_debug_snapshot(page, config, "huk24_login_required")
            logging.info("HUK24 Login weiterhin erforderlich nach Ladecheck: %s", page.url)
            browser.close()
            return result

        _save_debug_snapshot(page, config, "huk24_postfach")
        downloads = _download_pdf_links(page, config)
        context.storage_state(path=str(config.session_path))
        browser.close()

    result.files = downloads
    result.downloaded = len(downloads)
    return result


def _download_pdf_links(page, config: PortalProviderConfig) -> list[Path]:
    downloaded = []

    for label in ("PDF", "Download", "Herunterladen", "Rechnung"):
        candidates = page.locator("a, button").filter(has_text=label)
        count = candidates.count()
        logging.info("HUK24 Kandidaten mit Text '%s': %s", label, count)
        for index in range(min(count, 50)):
            locator = candidates.nth(index)
            try:
                with page.expect_download(timeout=10000) as download_info:
                    locator.click(timeout=5000)
                downloaded.append(_save_download(download_info.value, config.download_dir))
            except Exception as exc:
                logging.info("HUK24 Kandidat '%s' #%s hat keinen Download ausgeloest: %s", label, index, exc)
                continue

    pdf_links = page.locator("a[href*='.pdf']")
    pdf_link_count = pdf_links.count()
    logging.info("HUK24 direkte PDF-Links gefunden: %s", pdf_link_count)
    for index in range(min(pdf_link_count, 50)):
        locator = pdf_links.nth(index)
        try:
            with page.expect_download(timeout=10000) as download_info:
                locator.click(timeout=5000)
            downloaded.append(_save_download(download_info.value, config.download_dir))
        except Exception as exc:
            logging.info("HUK24 PDF-Link #%s hat keinen Download ausgeloest: %s", index, exc)
            continue

    unique = []
    seen = set()
    for path in downloaded:
        if path not in seen:
            unique.append(path)
            seen.add(path)
    return unique


def _wait_for_huk24_app(page, config: PortalProviderConfig) -> None:
    deadline_ms = config.wait_seconds * 1000
    step_ms = 1000
    elapsed = 0
    while elapsed < deadline_ms:
        body_text = page.locator("body").inner_text(timeout=5000).strip()
        skeleton_count = page.locator("[class*='skeleton'], [class*='loading'], [aria-busy='true']").count()
        actionable_count = page.locator("a, button").count()
        logging.info(
            "HUK24 Ladecheck: text_len=%s skeletons=%s actions=%s url=%s",
            len(body_text),
            skeleton_count,
            actionable_count,
            page.url,
        )
        if body_text and actionable_count > 0 and skeleton_count == 0:
            return
        page.wait_for_timeout(step_ms)
        elapsed += step_ms
    logging.info("HUK24 Wartezeit erreicht, pruefe aktuellen Seitenzustand trotzdem.")


def _save_debug_snapshot(page, config: PortalProviderConfig, name: str) -> None:
    if not config.debug_dir:
        return
    try:
        html_path = config.debug_dir / f"{name}.html"
        screenshot_path = config.debug_dir / f"{name}.png"
        html_path.write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(screenshot_path), full_page=True)
        logging.info("HUK24 Debug gespeichert: %s und %s", html_path, screenshot_path)
    except Exception as exc:
        logging.info("HUK24 Debug konnte nicht gespeichert werden: %s", exc)


def _save_download(download, download_dir: Path) -> Path:
    suggested = download.suggested_filename or "huk24_rechnung.pdf"
    if not suggested.lower().endswith(".pdf"):
        suggested = f"{Path(suggested).stem}.pdf"
    target = download_dir / suggested
    if target.exists():
        logging.info("Portal-Download existiert bereits: %s", target)
        return target
    download.save_as(str(target))
    logging.info("Portal-Download gespeichert: %s", target)
    return target


def _looks_like_login(page) -> bool:
    if "/zugang/anmelden" in page.url:
        return True
    text = page.locator("body").inner_text(timeout=5000).lower()
    login_words = ("einloggen", "login", "anmelden", "anmelden oder registrieren", "passwort", "zugangsdaten")
    return any(word in text for word in login_words)


def _accept_cookie_banner(page) -> None:
    for label in ("Mit erforderlichen Einstellungen fortfahren", "Zustimmen", "Alle akzeptieren"):
        try:
            button = page.get_by_role("button", name=label)
            if button.count() > 0:
                button.first.click(timeout=3000)
                logging.info("HUK24 Cookie-Dialog bestaetigt: %s", label)
                page.wait_for_timeout(1000)
                return
        except Exception:
            continue


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for counter in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Kein freier Dateiname gefunden fuer {path}")


def _load_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright ist nicht installiert. Bitte ausfuehren: "
            "../venv/bin/pip install playwright && ../venv/bin/playwright install chromium"
        ) from exc
    return sync_playwright
