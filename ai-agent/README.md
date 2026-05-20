# AI Agent Setup

Dieses Verzeichnis enthaelt die Python-Agenten fuer Home Assistant und den Rechnungs-Agenten.

Der Mac ist die Entwicklungsumgebung. Auf dem Zielsystem soll der Code spaeter in der Debian-VM auf dem Mini-PC laufen.

## Debian-Pakete

Auf dem Zielrechner zuerst die Systempakete installieren:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

Optional, aber hilfreich fuer bessere PDF-Erkennung als Fallback:

```bash
sudo apt install -y poppler-utils
```

`poppler-utils` liefert `pdftotext`. Der Rechnungs-Agent nutzt zuerst `pypdf`, kann aber auch `pdftotext` verwenden, falls es installiert ist.

### OCR fuer Bild-PDFs und Bild-Belege (optional, aber empfohlen)

Damit auch eingescannte oder fotografierte Rechnungen erkannt werden (Bild-PDFs ohne extrahierbaren Text sowie `.jpg/.png/.tif/...`), nutzt der Agent zusaetzlich Tesseract.

Debian/Ubuntu:

```bash
sudo apt install -y tesseract-ocr tesseract-ocr-deu poppler-utils
```

macOS (Homebrew):

```bash
brew install tesseract tesseract-lang poppler
```

Windows:

- Tesseract: `winget install UB-Mannheim.TesseractOCR` (deutsches Sprachpaket `deu` im Installer mit anhaken). Pfad zur `tesseract.exe` muss in `PATH` liegen.
- Poppler (optional, fuer `pdf2image`): https://github.com/oschwartz10612/poppler-windows — `bin`-Ordner in `PATH` aufnehmen. Alternativ wird `PyMuPDF` (siehe Python-Pakete unten) als reiner Python-Renderer ohne externes Binary verwendet.

Die zugehoerigen Python-Pakete (`pytesseract`, `Pillow`, `pdf2image`, `PyMuPDF`) stehen bereits in `requirements.txt` und werden mit `pip install -r requirements.txt` mitinstalliert.

OCR laesst sich ueber Environment-Variablen steuern:

```bash
INVOICE_OCR_DISABLE=1            # OCR komplett abschalten
INVOICE_OCR_LANG="deu+eng"       # Tesseract-Sprachen (Default: deu+eng)
INVOICE_OCR_MAX_PAGES=5          # max. Seiten pro PDF (Default: 5)
INVOICE_OCR_MAX_BYTES=41943040   # PDFs darueber werden uebersprungen (Default: 40 MB)
INVOICE_OCR_DPI=150              # Render-Aufloesung fuer PDF-OCR (Default: 150)
```

Fehlen Tesseract oder die Python-Pakete, ueberspringt der Agent OCR still und nutzt nur die bisherigen Textextraktoren.

### KI-Extraktion als Fallback

Der Rechnungs-Agent nutzt zuerst lokale Text-Extraktion und OCR. Wenn dabei zu wenig Vertrauen entsteht, kein Betrag gefunden wird oder ein Scan keinen lesbaren Text liefert, kann ein LLM/Vision-Modell den Beleg direkt analysieren.

In `config.yaml`:

```yaml
invoice_agent:
  ai_extraction:
    enabled: true
    min_confidence: 0.8
    max_file_bytes: 10485760
```

Die KI-Extraktion nutzt die zentrale `llm`-Konfiguration und die API-Keys aus `.env`, zum Beispiel `GEMINI_API_KEY`. Der Agent erwartet strukturiertes JSON vom Modell und uebernimmt Anbieter, Datum, Bruttobetrag, Waehrung, Kategorie und Konfidenz nur als Fallback/Verbesserung.

## Python-Umgebung

Lokale Entwicklung in diesem Projekt nutzt das gemeinsame `venv` auf Repo-Ebene. Aus dem Verzeichnis `ai-agent`:

```bash
../venv/bin/python -m pip install --upgrade pip
../venv/bin/pip install -r requirements.txt
```

Die Python-Pakete stehen in `requirements.txt`:

```text
google-genai
openai
playwright
python-dotenv
PyYAML
pypdf
requests
pytesseract
Pillow
pdf2image
PyMuPDF
openpyxl
```

Fuer Portal-Downloads wird zusaetzlich ein Playwright-Browser benoetigt:

```bash
../venv/bin/playwright install chromium
```

## Konfiguration

Die zentrale Konfiguration liegt in `config.yaml`.

Fuer Home Assistant gehoert der Long-Lived Access Token in `.env`:

```bash
HA-TOKEN="dein-home-assistant-token"
```

In `config.yaml` verweist `token_env` darauf:

```yaml
home_assistant:
  url: "http://homeassistant.local:8123"
  token_env: "HA-TOKEN"
```

Wichtige Pfade fuer den Rechnungs-Agenten:

```yaml
invoice_agent:
  inbox_dir: "./data/invoices/inbox"
  archive_dir: "./data/invoices/archive"
  review_dir: "./data/invoices/review"
  database_path: "./data/invoices/invoices.db"
  email_attachment_dir: "./data/invoices/extracted_email_attachments"
```

Auf Debian kannst du spaeter absolute Pfade verwenden, zum Beispiel:

```yaml
invoice_agent:
  inbox_dir: "/srv/agents/invoices/inbox"
  archive_dir: "/srv/agents/invoices/archive"
  review_dir: "/srv/agents/invoices/review"
  database_path: "/srv/agents/invoices/invoices.db"
  email_attachment_dir: "/srv/agents/invoices/extracted_email_attachments"
```

Secrets wie API-Keys gehoeren in `.env`, nicht ins Git-Repository.

## E-Mail-Anbindung ALL-INKL

Der Rechnungs-Agent kann per IMAP neue E-Mail-Anhaenge abholen und danach wie normale Dateien verarbeiten.

In `config.yaml`:

```yaml
invoice_agent:
  email:
    enabled: true
    host_env: "INVOICE_EMAIL_HOST"
    port: 993
    username_env: "INVOICE_EMAIL_USERNAME"
    password_env: "INVOICE_EMAIL_PASSWORD"
    mailbox: "INBOX"
    search: "ALL"
    mark_seen: false
    max_messages: 500
```

In `.env`:

```bash
INVOICE_EMAIL_HOST="wXXXXXXX.kasserver.com"
INVOICE_EMAIL_USERNAME="name@deinedomain.de"
INVOICE_EMAIL_PASSWORD="mailbox-passwort"
```

Als Vorlage gibt es `.env.example`.

Bei ALL-INKL ist der IMAP-Server typischerweise dein KAS-Login-Server, zum Beispiel `wXXXXXXX.kasserver.com`. Je nach Domain-Setup kann auch `imap.deinedomain.de` funktionieren. Der Port fuer IMAP mit SSL/TLS ist `993`.

Als Benutzername funktioniert bei ALL-INKL je nach Postfach-Konfiguration meistens die E-Mail-Adresse. Falls der Login damit nicht klappt, pruefe im KAS unter `E-Mail -> E-Mail-Postfach`, welcher Benutzername fuer das Postfach hinterlegt ist.

`search: "ALL"` holt gelesene und ungelesene Mails. Der Agent merkt sich verarbeitete Mail-UIDs zusaetzlich in `invoices.db`, damit im Dauerbetrieb nicht dieselbe Mail staendig neu verarbeitet wird.

Nuetzliche Varianten:

```yaml
search: "ALL"     # gelesene und ungelesene Mails
search: "UNSEEN"  # nur ungelesene Mails
search: "SEEN"    # nur gelesene Mails
```

`max_messages` begrenzt, wie viele gefundene Mails pro Lauf geprueft werden. Fuer den ersten grossen Import ist ein hoeherer Wert wie `500` oder `1000` sinnvoll. Danach kannst du wieder kleiner werden, zum Beispiel `50`.

Wenn du nur Rechnungen aus einem speziellen Ordner verarbeiten willst, lege im Mailkonto einen Ordner an, zum Beispiel `Rechnungen`, und setze:

```yaml
mailbox: "Rechnungen"
search: "ALL"
```

## Rechnungs-Agent starten

## Home-Assistant-Benachrichtigung

Der Agent kann nach einem Scan eine `persistent_notification` in Home Assistant erstellen.

In `config.yaml`:

```yaml
invoice_agent:
  home_assistant_notifications:
    enabled: true
    only_on_changes: true
    title: "Rechnungs-Agent"
    notification_id: "invoice_agent"
```

Mit `only_on_changes: true` meldet der Agent nur, wenn neue Rechnungen archiviert wurden oder Dateien in `review` gelandet sind. Reine Duplikat-Laeufe bleiben still.

Die Benachrichtigung nutzt die bestehende Home-Assistant-API-Konfiguration oben in `config.yaml`.

## Portal-Downloads HUK24

Fuer Anbieter wie HUK24, bei denen Rechnungen nur im Kundenportal liegen, nutzt der Agent Playwright mit einer gespeicherten Browser-Session.

In `config.yaml`:

```yaml
invoice_agent:
  portals:
    enabled: true
    providers:
      - name: "huk24"
        enabled: true
        url: "https://www.huk24.de/meine-huk24/postfach/"
        session_path: "./data/invoices/portal_sessions/huk24.json"
        download_dir: "./data/invoices/portal_downloads/huk24"
        headless: true
        wait_seconds: 20
```

Einmalig interaktiv einloggen:

```bash
../venv/bin/python agents/invoices.py --portal-login huk24
```

Dann im Browser bei HUK24 einloggen, ggf. 2FA bestaetigen und bis ins Postfach navigieren. Danach im Terminal Enter druecken. Der Agent speichert die Session unter `session_path`.

Danach laeuft HUK24 im normalen Scan mit:

```bash
../venv/bin/python agents/invoices.py --once
```

Nur HUK24 pruefen, ohne den kompletten Rechnungsbestand zu scannen:

```bash
../venv/bin/python agents/invoices.py --portal-check huk24
```

Der HUK24-Check schreibt Debug-Dateien nach `data/invoices/portal_debug/huk24`, damit man sehen kann, welche Postfach-Seite Playwright wirklich sieht.

Wenn HUK24 erneut Login oder 2FA verlangt, meldet der Agent das im Log. Dann `--portal-login huk24` erneut ausfuehren.

Wenn Home-Assistant-Benachrichtigungen aktiviert sind, sendet der Agent in diesem Fall zusaetzlich eine eigene Meldung:

```text
HUK24 Login erforderlich
```

Die Meldung enthaelt den passenden `--portal-login huk24` Befehl.

## Rechnungs-Agent starten

Einmaliger Lauf:

```bash
../venv/bin/python agents/invoices.py --once
```

Dauerbetrieb:

```bash
../venv/bin/python agents/invoices.py --watch
```

Bereits bekannte Dateien erneut auswerten, zum Beispiel nach Verbesserungen an der Erkennung:

```bash
../venv/bin/python agents/invoices.py --once --reprocess
```

## Archiv aufraeumen

Wenn nach Testlaeufen oder neu aufgebauter Datenbank mehrfach archivierte Dateien im `archive` liegen, kann der Cleanup-Agent Dateien finden, die nicht mehr in `invoices.db` referenziert sind.

Nur pruefen:

```bash
../venv/bin/python agents/cleanup_archive.py
```

Unreferenzierte Dateien in ein Backup verschieben:

```bash
../venv/bin/python agents/cleanup_archive.py --apply
```

Das Script loescht nichts direkt. Es verschiebt nach `data/invoices/archive_cleanup_backup/<timestamp>/`.

## Steuer-Export

Der Steuer-Export erzeugt eine Jahresuebersicht aus der bestehenden `invoices.db`. Das ist eine Vorbereitung fuer die Einkommensteuer, keine Steuerberatung.

Start:

```bash
../venv/bin/python agents/invoices.py --tax-year 2026
```

Erst Rechnungen scannen und danach direkt den Steuer-Export erzeugen:

```bash
../venv/bin/python agents/invoices.py --once --tax-year 2026
```

Der separate Agent bleibt als Kurzweg verfuegbar:

```bash
../venv/bin/python agents/tax_export.py --year 2026
```

Ausgabe:

```text
data/invoices/tax/2025/einkommensteuer_2025.csv
data/invoices/tax/2025/einkommensteuer_2025.xlsx
```

Die Excel-Datei enthaelt fuenf Tabellenblaetter (optimiert fuer Steuerberater/Finanzamt):

```text
Uebersicht   - Kennzahlen: Anzahl Belege, Summen EUR (gesamt / ohne Review), Erstellzeitpunkt
Alle Belege  - Detailliste mit Datums-/EUR-Format, Autofilter, Summenzeile, Review-Zeilen farbig
Monate       - Anzahl und Summe je Monat und Steuerkategorie
Kategorien   - Anzahl und Summe je Steuerkategorie
Review       - Belege, die manuell gepruefte werden muessen
```

Voraussetzung fuer das formatierte Excel ist das Paket `openpyxl` (in `requirements.txt` enthalten).
Ist es nicht installiert, faellt der Export auf einen einfachen XLSX-Writer ohne Formatierung zurueck.

Die CSV-Datei nutzt UTF-8 mit BOM und deutsche Formatierung (Datum `TT.MM.JJJJ`, Komma als Dezimaltrenner, Semikolon als Trennzeichen) - damit oeffnet Excel sie direkt korrekt.

Die Regeln stehen in `config.yaml` unter `tax_export.categories`. Nicht sicher zuordenbare oder auffaellige Belege landen in `Review`.

## Systemd-Service auf Debian

Beispiel fuer `/etc/systemd/system/invoice-agent.service`:

```ini
[Unit]
Description=Invoice AI Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/srv/agents/ai-agent
ExecStart=/srv/agents/ai-agent/venv/bin/python agents/invoices.py --watch
Restart=always
RestartSec=10
User=agent
Group=agent

[Install]
WantedBy=multi-user.target
```

Danach:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now invoice-agent
sudo systemctl status invoice-agent
```

Logs ansehen:

```bash
journalctl -u invoice-agent -f
```
