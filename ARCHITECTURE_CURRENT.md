# Systemübersicht

RoboterSteve ist aktuell ein lokales Agent-System aus FastAPI-Backend, React/Vite-Frontend und mehreren Agent-Modulen unter `agent-api/backend/agents`. Die Agenten sind nicht als komplett isolierte Prozesse modelliert, sondern als Python-Module mit Manifest, FastAPI-Router, Service-Klassen, optionalem Scheduler und eigener SQLite-Persistenz.

Der zentrale Einstiegspunkt ist `agent-api/backend/main.py`. Dort werden Auth, Home Assistant, Waste, Orchestrator, Agent Registry und Settings als Router eingebunden. Zusätzlich lädt `include_agent_routers(app)` alle aktivierten Agent-Router aus den Manifesten. Beim FastAPI-Startup werden über `agent_runtime_services()` Agent-Services gefunden und deren `start_scheduler()` aufgerufen, falls vorhanden.

Das Frontend ist eine React-Single-Page-App in `agent-api/frontend/src`. Es nutzt `api/client.ts` als zentrale API-Schicht und zeigt Agenten über `/agents`, Agent Map, Wall Dashboard, Finance/Invoice, MyWellness und Market Views an.

# Ordnerstruktur

```text
agent-api/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── paths.py
│   ├── api/
│   │   ├── auth_routes.py
│   │   ├── homeassistant_routes.py
│   │   ├── orchestrator_routes.py
│   │   ├── settings_routes.py
│   │   └── waste_routes.py
│   ├── agents/
│   │   ├── registry.py
│   │   ├── routes.py
│   │   ├── invoices/
│   │   ├── market/
│   │   ├── mywellness/
│   │   └── vacation/
│   └── services/
│       ├── auth_service.py
│       ├── homeassistant_service.py
│       ├── settings_service.py
│       ├── waste_service.py
│       ├── core/ha_client.py
│       └── llm/
├── data/
│   ├── invoices/
│   ├── market/
│   └── mywellness/
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── config.yaml
├── requirements.txt
├── DEPLOYMENT.md
└── agent-api.service
```

# Backend

`backend/main.py` erstellt die FastAPI-App, aktiviert CORS für Vite, schützt `/api/*` per JWT-Middleware und mountet das gebaute Frontend aus `frontend/dist`, wenn es existiert.

Router werden in dieser Reihenfolge eingebunden:

- `auth_router`
- `homeassistant_router`
- `orchestrator_router`
- `waste_router`
- `agents_router`
- dynamische Agent-Router via `include_agent_routers(app)`
- `settings_router`

Beim Startup/Shutdown werden dynamisch gefundene Runtime-Services gestartet bzw. gestoppt. Das ist aktuell der wichtigste Mechanismus für Agent-Scheduler.

# Frontend

Das Frontend liegt in `agent-api/frontend/src` und ist eine Vite/React-App.

Wichtige Bereiche:

- `App.tsx`: eigenes Routing anhand von `window.location.pathname`.
- `api/client.ts`: zentrale Fetch-Schicht mit JWT Bearer Token und API-Typen.
- `context/AuthContext.tsx`: Login-Status und Token-Verwaltung.
- `components/Layout.tsx`, `Sidebar.tsx`: normales App-Layout.
- `pages/WallDashboardPage.tsx`: Wall-/Smart-Home-UI mit Agent Map.
- `pages/AgentsPage.tsx`: Agent Console und Agent Map.
- `components/AgentMap.tsx`, `AgentNode.tsx`: ReactFlow-basierte Agent Map.
- `pages/finance/*`: Invoice-UI.
- `pages/mywellness/*` und `components/mywellness/*`: MyWellness-UI.
- `pages/market/*` und `components/market/*`: Market-UI.

Vite proxyed im Entwicklungsmodus `/api`, `/agents` und `/health` auf `http://127.0.0.1:8080`.

# Agenten

Alle Agenten besitzen aktuell ein `manifest.yaml`. Die Registry liest daraus:

- `id`
- `name`
- `description`
- `enabled`
- `status`
- `ui.icon`
- `ui.dashboard_route`
- `api.prefix`
- `api.route_module`
- `runtime.service_object`
- `settings`

## Invoice Agent

Verantwortung:

- Rechnungen/Belege hochladen.
- Dokumente speichern, archivieren und ausliefern.
- Metadaten extrahieren, optional KI-Analyse ausführen.
- Rechnungen kategorisieren, prüfen, exportieren.
- Agent-Status, Scheduler-Einstellungen und Laufstatus verwalten.

Datenbank:

- `agent-api/data/invoices/invoices.db`
- Tabellen laut vorhandener DB: `invoices`, `invoice_agent_settings`, `email_messages`

API Endpunkte:

- Prefix: `/api/invoices`
- `GET /summary`
- `GET /agent/status`
- `POST /agent/enable`
- `POST /agent/disable`
- `POST /agent/toggle`
- `PUT /agent/settings`
- `GET /years`
- `GET /years/{year}`
- `GET /years/{year}/months/{month}`
- `GET /exports/year/{year}/excel`
- `GET /exports/year/{year}/pdf`
- `GET /exports/year/{year}/zip`
- `GET /exports/month/{year}/{month}/excel`
- `GET /exports/month/{year}/{month}/pdf`
- `GET /exports/month/{year}/{month}/zip`
- `GET /{invoice_id}`
- `GET /{invoice_id}/file`
- `PUT /{invoice_id}`
- `POST /{invoice_id}/reanalyze`
- `POST /{invoice_id}/mark-reviewed`
- `DELETE /{invoice_id}`
- `POST /upload`
- `POST /run`
- `POST /cleanup-archive`

Services:

- `InvoiceService`
- `FileService`
- `ExportService`
- Hilfsmodule: `ai_extractor`, `archiver`, `catalog`, `categories`, `cleanup_archive`, `email`, `extractor`, `portals`, `scanner`, `tax_export`

## MyWellness Agent

Verantwortung:

- MyWellness-Kurse vorbereiten und buchen.
- Kursdaten, Buchungen, Agent-Läufe und Logs verwalten.
- Laufmodi `prepare` und `book`.
- Health-/Recovery-Daten aus Home Assistant bzw. Withings-Entities importieren und analysieren.
- Eigene Settings für Vorbereitung, Buchung, Zeiten, Tage und Wunschkurse speichern.

Datenbank:

- `agent-api/data/mywellness/mywellness.db`
- Tabellen laut vorhandener DB: `mywellness_settings`, `agent_runs`, `courses`, `mywellness_logs`, `mywellness_health_settings`, `mywellness_health_metrics`, `mywellness_recovery_reports`

API Endpunkte:

- Legacy/Kompatibilität:
  - `GET /api/agent/status`
  - `POST /api/agent/start`
  - `POST /api/agent/stop`
- MyWellness:
  - `GET /api/mywellness/status`
  - `POST /api/mywellness/run/prepare`
  - `POST /api/mywellness/run/book`
  - `POST /api/mywellness/enable`
  - `POST /api/mywellness/disable`
  - `POST /api/mywellness/toggle`
  - `PUT /api/mywellness/settings`
  - `GET /api/mywellness/courses`
  - `GET /api/mywellness/courses/upcoming`
  - `POST /api/mywellness/book`
  - `POST /api/mywellness/cancel`
  - `GET /api/mywellness/bookings`
  - `GET /api/mywellness/logs`
- Health:
  - `GET /api/mywellness/health/status`
  - `GET /api/mywellness/health/metrics`
  - `POST /api/mywellness/health/import-from-ha`
  - `POST /api/mywellness/health/analyze`
  - `GET /api/mywellness/health/latest-report`
  - `GET /api/mywellness/health/reports`
  - `PUT /api/mywellness/health/settings`
  - `GET /api/mywellness/health/withings/entities`
  - `POST /api/mywellness/health/withings/import`
  - `GET /api/mywellness/health/withings/latest`
  - `POST /api/mywellness/health/withings/discover`

Services:

- `MyWellnessService`
- `MyWellnessHealthService`
- `store.py` für SQLite-Zugriff und Schema
- `mywellness.py` als CLI/Agent-Logik
- `ai_service.py` für Health-/Recovery-Auswertung

## Market Agent

Verantwortung:

- Watchlist verwalten.
- Marktberichte erzeugen.
- Einzelsymbole analysieren.
- News, Quotes und technische/heuristische Signale zu Reports verdichten.
- Reports und News persistieren.

Datenbank:

- `agent-api/data/market/market.db`
- Tabellen laut vorhandener DB: `market_watchlist`, `market_reports`, `market_news`

API Endpunkte:

- Prefix: `/api/market`
- `GET /watchlist`
- `POST /watchlist`
- `PUT /watchlist/{item_id}`
- `DELETE /watchlist/{item_id}`
- `POST /run`
- `POST /analyze/{symbol}`
- `GET /reports`
- `GET /reports/latest`
- `GET /reports/{symbol}`
- `GET /reports/{symbol}/latest`
- `GET /summary`

Services:

- `MarketAgent`
- `MarketReportService`
- `data_service`
- `news_service`
- `analysis_service`
- `symbol_resolver`

## Vacation Agent

Verantwortung:

- Anwesenheits-/Urlaubsmodus rund um Home Assistant vorbereiten.
- Aktuell eher ein leichter Service/Stub als voll ausgebauter Agent.
- Liest `input_boolean.vacation_mode` aus Home Assistant.
- Speichert letzten Lauf und letzten Fehler im Speicher der Service-Instanz, nicht in einer eigenen DB.

Datenbank:

- Keine eigene SQLite-Datenbank vorhanden.

API Endpunkte:

- Prefix: `/api/vacation`
- `GET /status`
- `GET /config`
- `POST /run`

Services:

- `VacationService`
- Nutzt `HomeAssistantClient` aus `backend/services/core/ha_client.py`

# Gemeinsame Services

- `auth_service.py`: einfache JWT-Erzeugung/Validierung per HMAC SHA-256, Login gegen konfigurierte Username/Password-Werte.
- `settings_service.py`: aggregiert Konfigurationszustand, Pfade, Agent-Runtime-Settings und Integrationsstatus.
- `homeassistant_service.py`: moderne HTTPX-basierte Home-Assistant-Abstraktion für Wall, Status-Lesen, Templates und Service Calls.
- `core/ha_client.py`: ältere requests-basierte Home-Assistant-Abstraktion mit Convenience-Methoden wie `turn_on`, `turn_off`, `set_cover_position`, `notify`.
- `waste_service.py`: normalisiert Abfall-Status aus Home Assistant und erzeugt Erinnerungen auf Basis von Abfallterminen, Vacation Mode und Briefkastenstatus.
- `llm/*`: Provider-Abstraktion für OpenAI, Gemini und Llama. Die Factory referenziert auch Claude, aber ein `ClaudeLLMClient` ist im aktuellen Ordner nicht vorhanden.

# Home Assistant Integration

Aktuell existieren mehrere HA-Pfade:

- `HomeAssistantService` in `backend/services/homeassistant_service.py`
  - liest `HA_URL` und `HA_TOKEN` aus Environment, `.env` oder `config.yaml`
  - `get_states()`
  - `get_state(entity_id)`
  - `fetch_entity_state(entity_id)`
  - `render_template(template)`
  - `call_service(domain, service, payload)`
- `HomeAssistantClient` in `backend/services/core/ha_client.py`
  - ältere requests-basierte Variante
  - wird u.a. vom Vacation Agent genutzt
  - unterstützt Notifications und einfache Entity-Service-Calls
- `homeassistant_routes.py`
  - `GET /api/homeassistant/wall`
  - `POST /api/homeassistant/service`
  - erstellt Wall-Daten aus HA States: Lights, Covers, Sensors, Switches, Media Player, Climate, Weather, Security, Batteries, Waste und Agent Summary.
- `waste_service.py`
  - liest `sensor.abfall_naechster_termin`
  - liest Kontext aus `input_boolean.vacation_mode` und `input_boolean.post_im_briefkasten`
- MyWellness Health
  - importiert Health-/Withings-Metriken aus Home-Assistant-Entities.

# LLM Architektur

Die LLM-Konfiguration liegt in `agent-api/config.yaml` unter `llm`.

Aktuelle Provider-Struktur:

- `BaseLLMClient` definiert `generate()` und optional `generate_with_file()`.
- `factory.py` erzeugt Clients anhand von `llm.provider`.
- Vorhandene Clients:
  - `OpenAILLMClient`
  - `GeminiLLMClient`
  - `LlamaLLMClient`
- Konfigurierbare Provider in `config.yaml`:
  - `openai`
  - `gemini`
  - `claude`
  - `llama`

Hinweis: `factory.py` enthält einen `claude`-Zweig, aber im aktuellen `backend/services/llm` ist kein Claude-Client implementiert/importiert. Dieser Pfad ist deshalb aktuell nicht vollständig nutzbar.

# Datenbanken

Vorhandene SQLite-Datenbanken:

- `agent-api/data/invoices/invoices.db`
  - `invoices`
  - `invoice_agent_settings`
  - `email_messages`
- `agent-api/data/mywellness/mywellness.db`
  - `mywellness_settings`
  - `agent_runs`
  - `courses`
  - `mywellness_logs`
  - `mywellness_health_settings`
  - `mywellness_health_metrics`
  - `mywellness_recovery_reports`
- `agent-api/data/market/market.db`
  - `market_watchlist`
  - `market_reports`
  - `market_news`

Nicht vorhanden:

- keine `household.db`
- keine `orchestrator.db`
- keine eigene Vacation-Datenbank

# API Struktur

Querschnitts-APIs:

- `/api/auth`
  - Login und aktueller User
- `/api/settings`
  - aggregierter System-/Konfigurationsstatus
- `/api/homeassistant`
  - Wall-Daten und HA-Service-Calls
- `/api/waste`
  - Abfallstatus, nächster Termin, Erinnerungen
- `/api/orchestrator`
  - Agent-/Service-Map
- `/api/agents`
  - Manifest-basierte Agentenliste

Agent-APIs:

- `/api/invoices`
- `/api/market`
- `/api/mywellness`
- `/api/vacation`

Auth:

- Alle `/api/*`-Endpunkte außer `/api/auth/login` sind durch die Middleware in `main.py` geschützt.
- `/health` ist öffentlich.

# Deployment Struktur

Vorhanden:

- `agent-api/DEPLOYMENT.md`: beschreibt Deployment auf Debian mit systemd und gebautem Frontend.
- `agent-api/agent-api.service`: systemd-Unit-Datei im Repository.
- `frontend/dist`: gebaute React-App kann von FastAPI ausgeliefert werden.
- `frontend/package.json`: `dev`, `build`, `preview`.

Wichtige Beobachtung:

- `DEPLOYMENT.md` empfiehlt eine separate Environment-Datei unter `/etc/robotersteve-agent-api.env`.
- Die vorhandene `agent-api.service` enthält aktuell Environment-Werte direkt in der Unit-Datei. Für Produktivbetrieb ist die Variante aus `DEPLOYMENT.md` sauberer, weil Secrets nicht in einer Unit im Repo liegen sollten.

# Aktuelle Agent Registry

`backend/agents/registry.py` ist aktuell der zentrale Manifest-Lader und Plugin-ähnliche Integrationspunkt.

Aufgaben:

- findet `backend/agents/*/manifest.yaml`
- lädt Manifestdaten in `AgentManifest`
- stellt mit `public_dict()` sichere UI-/API-Metadaten bereit
- bindet aktivierte Agent-Router über `include_agent_routers(app)` dynamisch ein
- findet Runtime-Service-Objekte über `agent_runtime_services()`

Wichtig:

- `enabled: false` im Manifest verhindert aktuell das automatische Einbinden des Agent-Routers und das Starten seines Runtime-Service über die Registry.
- Die Registry speichert keinen Runtime-State.
- Die Registry persistiert nichts in einer Datenbank.
- Die Registry ist eher Discovery/Composition als Orchestrierung.

# Aktuelle Orchestrator Funktion

`backend/api/orchestrator_routes.py` stellt aktuell nur `GET /api/orchestrator/map` bereit.

Aufgaben:

- liest Agent-Manifeste über `discover_agent_manifests()`
- fragt Agent-Statusdaten direkt bei konkreten Services ab:
  - `invoice_service.status()`
  - `mywellness_service.status()`
  - `MarketReportService().summary()`
  - `vacation_service.status()`
- erzeugt eine Map aus Nodes und Edges:
  - Orchestrator
  - Agenten
  - Services `openai`, `database`, `homeassistant`
- berechnet Summary-Werte:
  - aktive Agenten
  - pausierte Agenten
  - Fehler
  - letzte Aktivität
  - nächste Aktivität

Bewertung:

- Es existiert ein impliziter Orchestrator als API-Aggregator.
- Er koordiniert noch keine Jobs, Queues oder Entscheidungen.
- Er persistiert keinen eigenen Zustand.
- Es gibt keine `orchestrator.db`.
- Die eigentliche Ausführung bleibt in den Agent-Services und deren eigenen Schedulern/Methoden.

