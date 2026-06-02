# RoboterSteve - AI Agent System

Lokales AI-Agent-System mit FastAPI-Backend, React-Frontend und integrierten Agenten fuer Home Assistant, Rechnungsverarbeitung, MyWellness, Vacation, Boersenanalyse und zentrale Zeitsteuerung. Zentrale Querschnittsdienste liefern Messaging, Household-Status und Infrastructure/FritzBox-Status ueber Home Assistant.

## Projektstruktur

```text
roboterSteve/
├── agent-api/                    # FastAPI-Backend + React-Frontend
│   ├── backend/
│   │   ├── main.py
│   │   ├── paths.py
│   │   ├── api/                  # Querschnitts-APIs: Auth, Settings, Orchestrator, Household, Infrastructure
│   │   ├── services/             # Querschnitts-Services (LLM, Home Assistant, Household, Infrastructure, Messaging)
│   │   └── agents/
│   │       ├── control.py        # Einheitlicher Agent-Control-Vertrag
│   │       ├── registry.py       # Manifest Discovery und Runtime-Service Lookup
│   │       ├── invoices/         # InvoiceAgent API, Service, Exporte, CLI
│   │       ├── market/           # MarketAgent API, Analyse-/Datenservices, CLI
│   │       ├── mywellness/       # MyWellness API, Agent, Scheduler-/Health-Services, CLI
│   │       ├── scheduler/        # Scheduler Agent V1, zentrale Task-Zeitsteuerung
│   │       └── vacation/         # Vacation Agent, Vacation Mode, Historie, Kalender, KI-Hinweise
│   ├── frontend/
│   │   └── src/                 # React-App
│   ├── config.yaml
│   └── requirements.txt
└── venv/                        # Gemeinsame Python-Umgebung
```

Agenten koennen optionale Scheduler-Defaults im eigenen `manifest.yaml` mitbringen. Der Scheduler registriert fehlende Defaults automatisch ueber `scheduler.tasks`, ohne bestehende lokale Tasks zu ueberschreiben.

## Entwicklung

### Backend (FastAPI)

```bash
cd agent-api
../venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload
```

### Frontend (React)

```bash
cd agent-api/frontend
npm install
npm run dev
```

### Zugriff

```text
Frontend: http://localhost:5173
Backend:  http://localhost:8080
Swagger:  http://localhost:8080/docs
```

Im lokalen Netzwerk ist Vite je nach Host-IP z.B. unter `http://192.168.178.143:5173` erreichbar.

## Python-Umgebung

Gemeinsame Python-Umgebung auf Repo-Ebene:

```bash
cd roboterSteve
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# oder venv\Scripts\activate  # Windows

pip install --upgrade pip
pip install -r agent-api/requirements.txt
```

Für Portal-Downloads wird zusätzlich Playwright benötigt:

```bash
pip install playwright
playwright install chromium
```

## Konfiguration

Die zentrale Konfiguration liegt in `config.yaml`.

### Logging

Die Anwendung verwendet genau eine zentrale App-Logdatei. Quelle der Wahrheit ist `logging.file` in `config.yaml`; relative Pfade werden relativ zu `agent-api/` aufgeloest.

```yaml
logging:
  file: "./logs/agent-api.log"
  level: INFO
```

Der FastAPI-Start, agentennahe CLI-Starts und die Settings API verwenden denselben Resolver. Die Settings-Seite zeigt deshalb unter `Storage -> Logdatei` den tatsaechlich verwendeten Pfad an.

### Home Assistant

```bash
# .env
HA_URL="http://homeassistant.local:8123"
HA_TOKEN="dein-home-assistant-token"
```

```yaml
# config.yaml
home_assistant:
  url: HA_URL
  token: HA_TOKEN
```

### Auth (Agent API)

Alle `/api/*`-Endpunkte außer `/api/auth/login` sind per JWT geschützt:

```bash
# .env
AGENT_API_USERNAME=admin
AGENT_API_PASSWORD=admin
AGENT_API_JWT_SECRET=dein-geheimer-schluessel
```

Lokaler Fallback für Entwicklung ist `admin` / `admin`. `AGENT_API_JWT_SECRET` sollte für echte Nutzung gesetzt werden.

### Infrastructure

Infrastructure ist ein zentraler Backend-Service, kein Agent. Home Assistant bleibt Datenquelle; es gibt keine direkte FritzBox API.

```yaml
infrastructure:
  enabled: true
  database_path: data/infrastructure/infrastructure.db
  entities:
    internet_status: ""
    fritzbox_status: ""
    connected_devices: ""
    wifi_status: ""
    wan_status: ""
    upload_speed: ""
    download_speed: ""
    external_ip: ""
    uptime: ""
```

Wenn Entity IDs leer sind, nutzt der Service robuste Home-Assistant-Discovery und ignoriert technische Entities wie Reload/Reconnect/Restart/Update/Identify.

## Agent API (Web-Interface)

### API-Endpunkte

**Auth:**
```text
POST /api/auth/login
GET  /api/auth/me
```

**Invoice:**
```text
GET    /api/invoices/summary
GET    /api/invoices/years
GET    /api/invoices/years/{year}
GET    /api/invoices/years/{year}/months/{month}
GET    /api/invoices/{invoice_id}
GET    /api/invoices/{invoice_id}/file
PUT    /api/invoices/{invoice_id}
POST   /api/invoices/{invoice_id}/reanalyze
POST   /api/invoices/{invoice_id}/mark-reviewed
DELETE /api/invoices/{invoice_id}
POST   /api/invoices/upload
POST   /api/invoices/run
```

**Export:**
```text
GET /api/invoices/exports/year/{year}/excel
GET /api/invoices/exports/year/{year}/pdf
GET /api/invoices/exports/year/{year}/zip
GET /api/invoices/exports/month/{year}/{month}/excel
GET /api/invoices/exports/month/{year}/{month}/pdf
GET /api/invoices/exports/month/{year}/{month}/zip
```

**MyWellness:**
```text
GET  /api/agent/status
POST /api/agent/start
POST /api/agent/stop
GET  /api/mywellness/status
POST /api/mywellness/run/prepare
POST /api/mywellness/run/book
POST /api/mywellness/enable
POST /api/mywellness/disable
POST /api/mywellness/toggle
PUT  /api/mywellness/settings
GET  /api/mywellness/courses
GET  /api/mywellness/courses/upcoming
POST /api/mywellness/book
POST /api/mywellness/cancel
GET  /api/mywellness/bookings
GET  /api/mywellness/logs
GET  /api/mywellness/health/status
GET  /api/mywellness/health/metrics
POST /api/mywellness/health/import-from-ha
POST /api/mywellness/health/analyze
GET  /api/mywellness/health/latest-report
GET  /api/mywellness/health/reports
PUT  /api/mywellness/health/settings
GET  /api/mywellness/health/withings/entities
POST /api/mywellness/health/withings/import
GET  /api/mywellness/health/withings/latest
POST /api/mywellness/health/withings/discover
GET  /api/mywellness/history/metrics
GET  /api/mywellness/history/recovery
GET  /api/mywellness/history/bookings
GET  /api/mywellness/history/trends
```

**Market:**
```text
GET    /api/market/status
POST   /api/market/enable
POST   /api/market/disable
POST   /api/market/toggle
POST   /api/market/run
GET    /api/market/summary
GET    /api/market/watchlist
POST   /api/market/watchlist
PUT    /api/market/watchlist/{id}
DELETE /api/market/watchlist/{id}
GET    /api/market/reports
GET    /api/market/reports/latest
POST   /api/market/analyze/{symbol}
```

**Vacation:**
```text
GET  /api/vacation/status
GET  /api/vacation/history
GET  /api/vacation/reminders
GET  /api/vacation/profiles
POST /api/vacation/enable
POST /api/vacation/disable
POST /api/vacation/toggle
PUT  /api/vacation/settings
POST /api/vacation/mode/enable
POST /api/vacation/mode/disable
POST /api/vacation/mode/toggle
GET  /api/vacation/ai/latest
POST /api/vacation/ai/analyze
```

**Agents / Orchestrator / Household / Infrastructure:**
```text
GET  /api/agents
GET  /api/orchestrator/map
GET  /api/orchestrator/agents/{agent_id}/control
POST /api/orchestrator/agents/{agent_id}/control/{action}
GET  /api/household/status
GET  /api/household/summary
GET  /api/household/reminders
GET  /api/infrastructure/status
GET  /api/infrastructure/summary
GET  /api/infrastructure/events
GET  /api/infrastructure/events/recent
GET  /api/infrastructure/outages
POST /api/infrastructure/check
GET  /api/homeassistant/wall
GET  /api/settings
GET  /api/waste/status
GET  /api/waste/next
GET  /api/waste/reminders
```

**Messaging:**
```text
GET    /api/messages
GET    /api/messages/unread-count
GET    /api/messages/source/{source}
POST   /api/messages
POST   /api/messages/{id}/read
POST   /api/messages/read-all
DELETE /api/messages/{id}
DELETE /api/messages
```

**Kompatible alte Endpunkte:**
```text
GET  /health
GET  /agents
GET  /agents/status
POST /agents/invoices/run
POST /agents/invoices/upload
POST /agents/vacation/run
```

## CLI-Agenten

Die CLI-Agenten sind in `backend/agents/` integriert und können direkt gestartet werden:

### Rechnungs-Agent

**Einmaliger Lauf:**
```bash
cd agent-api
../venv/bin/python -m backend.agents.invoices.invoices --once
```

**Dauerbetrieb:**
```bash
../venv/bin/python -m backend.agents.invoices.invoices --watch
```

**Bereits bekannte Dateien erneut auswerten:**
```bash
../venv/bin/python -m backend.agents.invoices.invoices --once --reprocess
```

**Steuer-Export:**
```bash
../venv/bin/python -m backend.agents.invoices.invoices --tax-year 2026
```

**Archiv aufräumen:**
```bash
# Nur prüfen
../venv/bin/python -m backend.agents.invoices.cleanup_archive

# Unreferenzierte Dateien in Backup verschieben
../venv/bin/python -m backend.agents.invoices.cleanup_archive --apply
```

### MyWellness-Agent

```bash
cd agent-api
../venv/bin/python -m backend.agents.mywellness.mywellness prepare  # Zielkurse suchen
../venv/bin/python -m backend.agents.mywellness.mywellness book     # Buchung versuchen
```

Erforderliche ENV-Werte:
```bash
MY_WELLNESS_TOKEN
MY_WELLNESS_USER_ID
MY_WELLNESS_FACILITY_ID
```

### Market-Agent

```bash
cd agent-api
../venv/bin/python -m backend.agents.market.market run
../venv/bin/python -m backend.agents.market.market analyze --symbol AAPL
```

Market Agent V1:

- Watchlist-Eingaben per Name, Symbol, ISIN oder WKN.
- Resolver normalisiert Symbol, Name, ISIN/WKN, Asset Type, Exchange und Waehrung.
- Analysen laufen nur durch manuellen Run oder Scheduler-Task, nicht beim Dashboard-Aufruf.
- Dashboard zeigt kompakte Signale, Discovery-Ideen und Watchlist-Signale; lange Marktberichte bleiben im Backend/Archiv.
- Signalwechsel werden ueber den Messaging Service gemeldet.

## Konfiguration - Rechnungs-Agent

```yaml
invoice_agent:
  inbox_dir: "./data/invoices/inbox"
  archive_dir: "./data/invoices/archive"
  review_dir: "./data/invoices/review"
  database_path: "./data/invoices/invoices.db"
  email_attachment_dir: "./data/invoices/inbox"
  ai_extraction:
    enabled: true
    always_for_documents: true
    min_confidence: 0.8
    max_file_bytes: 10485760
  archive_cleanup:
    enabled: true
    apply: true
    backup_dir: "./data/invoices/archive_cleanup_backup"
```

### E-Mail-Anbindung (ALL-INKL)

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

```bash
# .env
INVOICE_EMAIL_HOST="wXXXXXXX.kasserver.com"
INVOICE_EMAIL_USERNAME="name@deinedomain.de"
INVOICE_EMAIL_PASSWORD="mailbox-passwort"
```

### Home-Assistant-Benachrichtigung

```yaml
invoice_agent:
  home_assistant_notifications:
    enabled: true
    only_on_changes: true
    title: "Rechnungs-Agent"
    notification_id: "invoice_agent"
    notify_service: "notify.mobile_app_system_error_404"
    persistent: true
```

### Portal-Downloads (HUK24)

```yaml
invoice_agent:
  portals:
    enabled: true
    providers:
      - name: "huk24"
        enabled: true
        url: "https://www.huk24.de/meine-huk24/postfach/"
        session_path: "./data/invoices/portal_sessions/huk24.json"
        download_dir: "./data/invoices/inbox"
        headless: true
        wait_seconds: 20
```

**Einmalig einloggen:**
```bash
../venv/bin/python -m backend.agents.invoices.invoices --portal-login huk24
```

**Portal prüfen:**
```bash
../venv/bin/python -m backend.agents.invoices.invoices --portal-check huk24
```

## Konfiguration - MyWellness-Agent

```yaml
agents:
  mywellness:
    token: MY_WELLNESS_TOKEN
    user_id: MY_WELLNESS_USER_ID
    facility_id: MY_WELLNESS_FACILITY_ID
    desired_courses:
      - "Cross-Power"
      - "Body Workout"
      - "Functional Training"
    days: 2
    prepare_time: "17:00"
    booking_time: "20:59:58"
    database_path: "./data/mywellness/mywellness.db"
    log_path: "./logs/mywellness.log"
```

## Produktion

### Frontend builden

```bash
cd agent-api/frontend
npm run build
```

### Backend starten

```bash
cd agent-api
../venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

Wenn `frontend/dist` existiert, liefert FastAPI die gebaute React-App direkt aus.

### Systemd-Service (Debian)

Beispiel für `/etc/systemd/system/invoice-agent.service`:

```ini
[Unit]
Description=Invoice AI Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/srv/agents/agent-api
ExecStart=/srv/agents/agent-api/venv/bin/python -m backend.agents.invoices.invoices --watch
Restart=always
RestartSec=10
User=agent
Group=agent

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now invoice-agent
sudo systemctl status invoice-agent
journalctl -u invoice-agent -f
```

## Agent Plugin Contract

Ein neuer Agent wird als Ordner unter `agent-api/backend/agents/<id>/` angelegt.

**Minimaler Aufbau:**
```text
backend/agents/example/
  manifest.yaml
  routes.py
  service.py
```

**manifest.yaml:**
```yaml
id: example
name: Example Agent
description: Kurzbeschreibung fuer die Agenten-Uebersicht.
status: active
api:
  prefix: /api/example
  route_module: backend.agents.example.routes
runtime:
  service_object: example_service
ui:
  icon: Bot
  dashboard_route:
settings: {}
```

`enabled` gehoert nicht ins Manifest. Ob ein Agent aktiv ist, wird aus `backend/agents/<id>/config.yaml` gelesen:

```yaml
example:
  enabled: true
```

`routes.py` muss einen FastAPI-`router` exportieren. Wenn `runtime.service_object` gesetzt ist und dieses Objekt `start_scheduler()` / `stop_scheduler()` besitzt, ruft die API diese Methoden beim Starten und Stoppen automatisch auf.

### Orchestrator Control Contract

Der Orchestrator steuert Agenten ueber einen einheitlichen Control-Vertrag. Capabilities werden aus dem `runtime.service_object` des Manifests abgeleitet.

Unterstuetzte Control-Aktionen:

- `status`
- `start`
- `stop`
- `enable`
- `disable`
- `toggle`
- `run`

Moegliche Service-Methoden:

- `status() -> dict`
- `start() -> dict` oder `start_scheduler() -> None`
- `stop() -> dict` oder `stop_scheduler() -> None`
- `enable() -> dict`
- `disable() -> dict`
- `toggle() -> dict`
- `run(...) -> dict`, `run_agent() -> dict` oder `run_action(...) -> dict`

Regeln:

- `stop_scheduler()` darf keine Datenbanken loeschen und keine Agent-Fachdaten veraendern.
- `disable()` darf bestehende APIs nicht entfernen; es aendert nur Laufzeit-/Planungsstatus.
- `enable()` und `disable()` sollen idempotent sein.
- Statuswerte fuer den Orchestrator muessen auf `active`, `running`, `paused`, `disabled`, `error` abbildbar sein.
- Agent-Metadaten wie Name, Icon und Description kommen weiter ausschliesslich aus `manifest.yaml`.
- Fachlogik bleibt im Agenten; der Orchestrator ruft nur den Control-Vertrag auf.

Aktuelle Orchestrator-Control-Endpunkte:

- `GET /api/orchestrator/agents/{agent_id}/control`
- `POST /api/orchestrator/agents/{agent_id}/control/{action}`

Diese Endpunkte ersetzen bestehende Agent-APIs nicht, sondern liegen als zentrale Steuerungsschicht darueber. Unsupported Actions liefern `405`.

**Bekannte UI-Icons:** `Bot`, `FileText`, `Dumbbell`, `LineChart`, `Mail`, `CalendarCheck`, `Home`, `Settings2`.

## Hinweise

- JWT-Login ist aktiv; nur `/health` und `/api/auth/login` sind öffentlich.
- ELSTER-Direktversand ist nicht implementiert und wird nur als deaktivierter Platzhalter angezeigt.
- Steuerkategorien sind nur Datenfelder, keine Steuerberatung.
- Secrets wie API-Keys gehören in `.env`, nicht ins Git-Repository.
- Die KI-Extraktion für Belege nutzt die zentrale `llm`-Konfiguration und die API-Keys aus `.env`.
