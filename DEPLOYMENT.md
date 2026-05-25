# RoboterSteve Agent API Deployment

Diese Anleitung beschreibt das Deployment auf einem Debian-Zielrechner. Ziel ist:

- FastAPI laeuft als systemd-Service auf Port `8080`
- Die gebaute React-GUI wird direkt von FastAPI ausgeliefert
- Zugriff im Browser ueber `http://robotersteve.local:8080`
- `agent-api` und `ai-agent` liegen nebeneinander

## Zielstruktur

```text
/opt/roboterSteve/
├── agent-api/
│   ├── backend/
│   ├── frontend/
│   ├── config.yaml
│   └── requirements.txt
├── ai-agent/
│   ├── config.yaml
│   ├── .env
│   ├── data/
│   └── requirements.txt
└── venv/
```

Wichtig: Die Pfade im Projekt erwarten `agent-api` und `ai-agent` als Geschwisterordner.

## Debian vorbereiten

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nodejs npm avahi-daemon rsync
sudo hostnamectl set-hostname robotersteve
sudo systemctl enable --now avahi-daemon
```

Danach ist der Rechner im lokalen Netzwerk erreichbar unter:

```text
http://robotersteve.local:8080
```

Falls eine Firewall aktiv ist:

```bash
sudo ufw allow 8080/tcp
sudo ufw allow 5353/udp
```

## Dateien deployen

Vom Entwicklungsrechner:

```bash
rsync -av --delete \
  --exclude 'frontend/node_modules' \
  --exclude 'frontend/dist' \
  --exclude '__pycache__' \
  agent-api/ user@ziel:/opt/roboterSteve/agent-api/

rsync -av --delete \
  --exclude '__pycache__' \
  ai-agent/ user@ziel:/opt/roboterSteve/ai-agent/
```

Wenn du Rechnungsdaten uebernehmen willst, muessen Datenbank und Dokumente mitkopiert werden:

```bash
rsync -av ai-agent/data/invoices/ user@ziel:/opt/roboterSteve/ai-agent/data/invoices/
```

## Python-Umgebung installieren

Auf dem Zielrechner:

```bash
cd /opt/roboterSteve
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r agent-api/requirements.txt
./venv/bin/pip install -r ai-agent/requirements.txt
```

Der zweite Requirements-Schritt ist wichtig, weil `ai-agent` z.B. `requests`, `python-dotenv`, `openai` und weitere Agent-Abhaengigkeiten braucht.

## Frontend bauen

```bash
cd /opt/roboterSteve/agent-api/frontend
npm install
npm run build
```

Wenn `agent-api/frontend/dist` existiert, liefert FastAPI die GUI direkt unter Port `8080` aus.

## Umgebungsvariablen

Secrets sollten nicht direkt ins Git-Repo. Lege auf dem Zielrechner eine Environment-Datei an:

```bash
sudo nano /etc/robotersteve-agent-api.env
```

Beispiel:

```ini
AGENT_API_USERNAME=admin
AGENT_API_PASSWORD=change-me
AGENT_API_JWT_SECRET=change-me-long-random-secret

MY_WELLNESS_TOKEN=change-me
MY_WELLNESS_USER_ID=change-me
MY_WELLNESS_FACILITY_ID=change-me

INVOICE_EMAIL_HOST=imap.example.com
INVOICE_EMAIL_USERNAME=user@example.com
INVOICE_EMAIL_PASSWORD=change-me

OPENAI_API_KEY=change-me
GEMINI_API_KEY=change-me
CLAUDE_API_KEY=change-me
```

Rechte setzen:

```bash
sudo chmod 600 /etc/robotersteve-agent-api.env
```

Hinweis: Environment-Variablennamen mit Bindestrich sind ungueltig. Verwende z.B. `HA_TOKEN`, nicht `HA-TOKEN`.

## systemd-Service

Datei erstellen:

```bash
sudo nano /etc/systemd/system/agent-api.service
```

Inhalt:

```ini
[Unit]
Description=RoboterSteve Agent API
After=network.target

[Service]
WorkingDirectory=/opt/roboterSteve/agent-api
EnvironmentFile=/etc/robotersteve-agent-api.env
ExecStart=/opt/roboterSteve/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Service aktivieren:

```bash
sudo systemctl daemon-reload
sudo systemctl enable agent-api
sudo systemctl start agent-api
```

Pruefen:

```bash
sudo systemctl status agent-api
journalctl -u agent-api -f
```

## Betrieb

Start:

```bash
sudo systemctl start agent-api
```

Stop:

```bash
sudo systemctl stop agent-api
```

Restart nach Code- oder Config-Aenderung:

```bash
sudo systemctl restart agent-api
```

Nach Aenderung an `/etc/systemd/system/agent-api.service`:

```bash
sudo systemctl daemon-reload
sudo systemctl restart agent-api
```

Autostart deaktivieren:

```bash
sudo systemctl disable agent-api
```

## Zugriff

GUI:

```text
http://robotersteve.local:8080
```

Swagger/API:

```text
http://robotersteve.local:8080/docs
```

Healthcheck:

```bash
curl http://robotersteve.local:8080/health
```

## Update-Deployment

Auf dem Entwicklungsrechner:

```bash
rsync -av --delete \
  --exclude 'frontend/node_modules' \
  --exclude 'frontend/dist' \
  --exclude '__pycache__' \
  agent-api/ user@ziel:/opt/roboterSteve/agent-api/
```

Auf dem Zielrechner:

```bash
cd /opt/roboterSteve/agent-api/frontend
npm install
npm run build

cd /opt/roboterSteve
./venv/bin/pip install -r agent-api/requirements.txt
./venv/bin/pip install -r ai-agent/requirements.txt

sudo systemctl restart agent-api
```

## Typische Fehler

### `ModuleNotFoundError: No module named 'requests'`

`ai-agent/requirements.txt` wurde nicht installiert:

```bash
cd /opt/roboterSteve
./venv/bin/pip install -r ai-agent/requirements.txt
sudo systemctl restart agent-api
```

### `{"detail":"Document file not found"}`

Die Invoice-Datenbank zeigt auf Dateien, die auf dem Zielrechner fehlen oder frueher absolute Pfade vom Entwicklungsrechner hatten.

Pruefen:

```bash
ls -la /opt/roboterSteve/ai-agent/data/invoices/archive
ls -la /opt/roboterSteve/ai-agent/data/invoices/invoices.db
```

Daten erneut kopieren:

```bash
rsync -av ai-agent/data/invoices/ user@ziel:/opt/roboterSteve/ai-agent/data/invoices/
sudo systemctl restart agent-api
```

### Refresh auf Unterseiten liefert `{"detail":"Not Found"}`

Der Backend-Code muss den SPA-Fallback fuer React enthalten. Danach neu deployen und Service restarten.

### `robotersteve.local` wird nicht gefunden

Auf dem Zielrechner:

```bash
hostname
systemctl status avahi-daemon
sudo systemctl restart avahi-daemon
```

Vom Client:

```bash
ping robotersteve.local
```

Falls es weiter nicht geht, pruefe Router, VLAN/Gastnetz und Firewall.

