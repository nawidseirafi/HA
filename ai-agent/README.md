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

## Python-Umgebung

Im Verzeichnis `HA/ai-agent`:

```bash
python3 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

Die Python-Pakete stehen in `requirements.txt`:

```text
google-genai
openai
python-dotenv
PyYAML
pypdf
requests
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

## Rechnungs-Agent starten

Einmaliger Lauf:

```bash
./venv/bin/python agents/invoices.py --once
```

Dauerbetrieb:

```bash
./venv/bin/python agents/invoices.py --watch
```

Bereits bekannte Dateien erneut auswerten, zum Beispiel nach Verbesserungen an der Erkennung:

```bash
./venv/bin/python agents/invoices.py --once --reprocess
```

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
