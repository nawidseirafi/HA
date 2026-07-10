# RoboterSteve Architektur README - Ist-Zustand

Stand: 2026-06-09

Dieses Dokument beschreibt den aktuellen Zustand des Projekts nach P1, P2, Infrastructure Service V1, P2.5 Agent-Control, zentralem Messaging Service sowie Vacation/MyWellness/Invoice/Garden-Erweiterungen. Es ist keine Zielarchitektur und keine Umbauanleitung, sondern eine technische Bestandsaufnahme des laufenden Systems.

# Systemuebersicht

RoboterSteve besteht aktuell aus einer FastAPI-Backend-Anwendung und einem React/Vite-Frontend unter `agent-api/`. Das Projekt bleibt ein gemeinsames Entwicklungsrepo, kann aber ueber Editionen unterschiedliche Deployment-Zuschnitte bauen.

Der Backend-Einstieg ist:

```text
agent-api/backend/main.py
```

Das Backend bindet zentrale Router edition-aware ein:

- Auth
- Agents
- Orchestrator
- Household
- Infrastructure
- Home Assistant Wall API
- Messaging
- Waste
- Settings
- dynamisch geladene Agent-Router aus Manifesten

Die aktive Edition wird ueber `ROBOTERSTEVE_EDITION`, danach `config.yaml -> edition.name`, danach `personal` bestimmt. Ohne explizite Edition entspricht `personal` dem bisherigen privaten System.

Das Frontend liegt unter:

```text
agent-api/frontend/
```

Der gemeinsame Vite-Einstieg ist `frontend/src/main.tsx`. Dieser waehlt ueber die Backend-Editionserkennung und als Fallback ueber `VITE_ROBOTERSTEVE_EDITION` die Produkt-App. `personal` ist die private RoboterSteve-Anwendung; `sentero` ist eine eigene mobile-first Produktoberflaeche mit Onboarding, Dashboard, Verlauf, Raeumen, Kontakten und Einstellungen.

Wichtige UI-Bereiche:

- Agent Console
- Agent Map
- Nachrichten-Bereich der Agent Console (`/agents/messages`)
- Wall Dashboard
- System/Settings
- Invoice Dashboard
- MyWellness Dashboard
- Market Dashboard
- Vacation Dashboard
- Message Center im Wall Dashboard

Die Sidebar trennt zwei Navigationskontexte:

- Global Console Context: `Uebersicht`, `Agenten`, `Agent Map`, `Nachrichten`, `System`, `Abmelden`
- Agent Detail Context: `Zur Agent Console` plus nur agent-spezifische Menuepunkte und `Abmelden`

Globale Agent-Console-Menuepunkte werden in Agent-Dashboards nicht mehr angezeigt.

# Ordnerstruktur

```text
agent-api/
├── backend/
│   ├── agents/
│   │   ├── control.py
│   │   ├── registry.py
│   │   ├── routes.py
│   │   ├── garden/
│   │   ├── invoices/
│   │   ├── market/
│   │   ├── mywellness/
│   │   ├── scheduler/
│   │   ├── sentero/
│   │   └── vacation/
│   ├── api/
│   │   ├── auth_routes.py
│   │   ├── homeassistant_routes.py
│   │   ├── household_routes.py
│   │   ├── infrastructure_routes.py
│   │   ├── orchestrator_routes.py
│   │   ├── settings_routes.py
│   │   └── waste_routes.py
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── homeassistant_service.py
│   │   ├── household_service.py
│   │   ├── infrastructure_service.py
│   │   ├── messaging/
│   │   ├── orchestrator_control_service.py
│   │   ├── settings_service.py
│   │   ├── waste_service.py
│   │   ├── core/ha_client.py
│   │   └── llm/
│   ├── config.py
│   ├── main.py
│   └── paths.py
├── data/
│   ├── garden/
│   ├── invoices/
│   ├── infrastructure/
│   ├── market/
│   ├── messaging/
│   ├── mywellness/
│   └── scheduler/
├── editions/
│   ├── personal.yaml
│   └── sentero.yaml
├── tools/
│   └── build_edition.py
├── frontend/
│   └── src/
│       ├── main.tsx
│       ├── shared/
│       └── apps/
│           ├── personal/
│           └── sentero/
└── config.yaml
```

# Backend

`backend/main.py` erstellt die FastAPI-App, setzt CORS, JWT-Schutz fuer `/api/*`, OpenAPI-BearerAuth und statisches Frontend-Serving.

Oeffentliche Pfade:

- `GET /health`
- `POST /api/auth/login`

Alle anderen `/api/*`-Endpunkte laufen durch die bestehende Auth-Middleware.

Beim Startup ruft `main.py` ueber `agent_runtime_services()` fuer aktivierte Agenten optional `start_scheduler()` auf. Beim Shutdown wird optional `stop_scheduler()` aufgerufen.

# Agent Registry

Die Registry liegt in:

```text
agent-api/backend/agents/registry.py
```

Aufgaben:

- aktive Edition laden und erlaubte Agenten bestimmen
- `backend/agents/*/manifest.yaml` entdecken
- Manifestdaten in `AgentManifest` laden
- sichere Metadaten per `public_dict()` bereitstellen
- Agent-Router dynamisch und edition-gefiltert einbinden
- Runtime-Service-Objekte nur fuer erlaubte Agenten finden
- Agent-Control-Adapter per `get_agent_control(agent_id)` bereitstellen

Aktuell gilt:

- Agent-Router werden eingebunden, wenn ein `route_module` vorhanden ist und der Agent in der aktiven Edition erlaubt ist. Runtime-Disabled darf APIs innerhalb der Edition nicht entfernen, weil sonst Enable/Status-Endpunkte nicht erreichbar waeren.
- `agent_runtime_services()` startet Scheduler/Runtime-Dienste nur fuer aktivierte Agenten.
- `get_agent_control(agent_id)` kann ein Service-Objekt ueber `runtime.service_object` finden, wenn `route_module` importierbar ist.
- Die Registry speichert keinen Runtime-State und nutzt keine eigene Datenbank.


# Edition Runtime

Editionen sind additive Deployment-Zuschnitte innerhalb desselben Repos.

Dateien:

```text
agent-api/editions/personal.yaml
agent-api/editions/sentero.yaml
agent-api/backend/editions.py
agent-api/tools/build_edition.py
```

Eine Edition beschreibt:

- `name`
- `description`
- `enabled_agents`
- `enabled_core_services`
- `frontend_app`
- `include_frontend`
- `include_data`
- `include_files`
- `exclude_files`
- `config_template`

Runtime-Fallback:

1. `ROBOTERSTEVE_EDITION`
2. `config.yaml -> edition.name`
3. `personal`

Edition-Auswirkungen:

- `discover_agent_manifests()` liefert nur Agenten der aktiven Edition.
- `include_agent_routers(app)` bindet nur erlaubte Agent-Router ein.
- `agent_runtime_services()` startet nur erlaubte Runtime-Services.
- `/api/agents` und `/api/orchestrator/map` zeigen nur erlaubte Agenten.
- Core-Router in `backend/main.py` werden anhand `enabled_core_services` lazy eingebunden.
- Der Scheduler liest Manifest-Default-Tasks nur fuer Agenten der aktiven Edition.
- Edition-Builds enthalten `editions/edition.lock`; in diesem Build-Kontext gibt es keinen stillen Fallback auf `personal`.

Build-Ausgaben entstehen unter:

```text
agent-api/build/<edition>/
```

Private Daten werden nicht kopiert: `data/`, `logs/`, `.env`, `*.db`, `__pycache__/`, `venv/`, `.venv/`, `node_modules/`, `.DS_Store`.

# Agent-Control-Vertrag

Der gemeinsame Control-Vertrag liegt in:

```text
agent-api/backend/agents/control.py
```

Unterstuetzte Aktionen:

- `status`
- `start`
- `stop`
- `enable`
- `disable`
- `toggle`
- `run`

Nicht jeder Agent muss alle Aktionen anbieten. Der Adapter ermittelt Capabilities aus vorhandenen Methoden am Service-Objekt.

Generische Methodenzuordnung:

- `status` -> `service.status()`
- `start` -> `service.start()` oder `service.start_scheduler()`
- `stop` -> `service.stop()` oder `service.stop_scheduler()`
- `enable` -> `service.enable()`
- `disable` -> `service.disable()`
- `toggle` -> `service.toggle()`
- `run` -> `service.run()`, `service.run_agent()` oder `service.run_action()`

Control-Ergebnis:

```json
{
  "agent_id": "mywellness",
  "action": "start",
  "ok": true,
  "status": "running",
  "message": "Agent start ausgefuehrt.",
  "data": {}
}
```

# Scheduler Agent

Status: Version 1.0 umgesetzt.

Der Scheduler Agent ist die zentrale Zeitsteuerung der Plattform. Er besitzt keine Fachlogik, sondern entscheidet nur, wann definierte Tasks ausgefuehrt werden. Die Ausfuehrung erfolgt ueber bestehende Agent-Control-Actions oder reine Service-Checks.

Dateien:

```text
backend/agents/scheduler/
data/scheduler/scheduler.db
```

Unterstuetzte Schedule-Typen:

- `once`
- `recurring`
- `cron`
- `condition`

Unterstuetzte Actions:

- `start_agent`
- `stop_agent`
- `execute_action`
- `create_message`
- `call_webhook`
- `http_request`
- `infrastructure_check`
- `household_check`

Standard-Tasks:

- Market Analyse um 18:00
- Infrastructure Health Check taeglich um 07:00
- Vacation Statuspruefung taeglich
- Garden Statuspruefung taeglich um 07:00
- Household Fensterpruefung um 22:00
- Invoice Agent Lauf um 22:00
- MyWellness Prepare um 17:00 und Book um 20:59

Agenten koennen eigene Scheduler-Defaults in ihrem `manifest.yaml` deklarieren:

```yaml
scheduler:
  tasks:
    - default_key: example:run:0800
      name: Beispiel Agent Lauf 08:00
      schedule_type: recurring
      schedule:
        time: "08:00"
      target_action: run
```

Der Scheduler registriert fehlende Manifest-Tasks beim Start automatisch. Bestehende Tasks werden anhand von `default_key` oder Name erkannt und nicht ueberschrieben, damit lokal geaenderte Zeiten erhalten bleiben.

Der Scheduler ist ueber den gemeinsamen Agent-Control-Vertrag steuerbar:

```text
GET  /api/orchestrator/agents/scheduler/control
POST /api/orchestrator/agents/scheduler/control/{action}
```

Eigene API:

```text
GET  /api/scheduler/status
GET  /api/scheduler/summary
GET  /api/scheduler/tasks
GET  /api/scheduler/runs
POST /api/scheduler/run
POST /api/scheduler/tasks/{id}/run
POST /api/scheduler/tasks/{id}/enable
POST /api/scheduler/tasks/{id}/disable
```

Wichtige Scheduler-Ereignisse werden ueber den Messaging Service als Orchestrator-Nachrichten erzeugt.

# Orchestrator

Der Orchestrator besteht aktuell aus zwei Teilen:

```text
agent-api/backend/api/orchestrator_routes.py
agent-api/backend/services/orchestrator_control_service.py
```

## Orchestrator Map

`GET /api/orchestrator/map` ist die zentrale Datenquelle fuer die Agent Map im Frontend.

Die Map enthaelt:

- Orchestrator Node
- Agent Nodes aus Manifesten
- Service Nodes `openai`, `database`, `homeassistant`
- Edges vom Orchestrator zu Agenten
- Edges von Agenten zu Datenbank/OpenAI/Home Assistant
- normalisierte Statuswerte
- Control-Informationen je Node
- Agent-Runtime-Status wird generisch ueber den Agent-Control-Vertrag (`status`) gelesen; keine Agent-Sonderlogik in der Map.

Statuswerte:

- `active`
- `running`
- `disabled`
- `error`

`paused` ist als UI-/Zukunftswert bekannt, gehoert aber nicht zum Basisstatus der aktuell angeglichenen Agenten.

Agent-Metadaten wie Name, Icon und Description kommen aus Manifesten.

Beispiel Control-Feld:

```json
{
  "control": {
    "supported": true,
    "actions": ["status", "start", "stop", "enable", "disable", "toggle", "run"]
  }
}
```

Service Nodes sind read-only:

```json
{
  "control": {
    "supported": false,
    "actions": []
  }
}
```

## Orchestrator Control API

Aktuelle Endpunkte:

- `GET /api/orchestrator/agents/{agent_id}/control`
- `POST /api/orchestrator/agents/{agent_id}/control/{action}`

Der Control Service:

- validiert, ob der Agent im Manifest existiert
- liest Capabilities ueber die Registry
- fuehrt Aktionen nur ueber den generischen Control-Vertrag aus
- enthaelt keine direkten Imports auf einzelne Agenten
- liefert `405`, wenn eine Aktion nicht unterstuetzt wird
- verwendet keine `orchestrator.db`

Auch die Orchestrator Map nutzt fuer Agent-Status denselben generischen Control-Vertrag.

Aktuell erkannte Capabilities:

```text
invoices:    status, start, stop, enable, disable, toggle, run
garden:      status, enable, disable, toggle, run
market:      status, enable, disable, toggle, run
mywellness:  status, start, stop, enable, disable, toggle, run
vacation:    status, start, stop, enable, disable, toggle, run
```

# Agenten

## Invoice Agent

Ordner:

```text
agent-api/backend/agents/invoices/
```

Manifest:

```text
agent-api/backend/agents/invoices/manifest.yaml
```

Verantwortung:

- Belege hochladen
- Rechnungen extrahieren
- KI-Auswertung
- Review-Status
- Export nach Excel/PDF/ZIP
- E-Mail- und optional Portal-Import
- Archiv-Cleanup fuer unreferenzierte Dateien

Datenbank:

```text
agent-api/data/invoices/invoices.db
```

Wichtige Services:

- `service.py`
- `catalog.py`
- `file_service.py`
- `export_service.py`
- `ai_extractor.py`
- `scanner.py`

Control:

- `status`
- `start`
- `stop`
- `enable`
- `disable`
- `toggle`
- `run`

Hinweis: `start`/`stop` werden ueber Scheduler-Methoden abgebildet, `run` ueber `run_agent()`.

Archiv-Cleanup:

- Referenzierte Archivdateien werden gegen alte und neue Projektpfade aufgeloest.
- Alte absolute Pfade wie `.../ai-agent/data/invoices/archive/...` werden auf das aktuelle `agent-api/data/invoices/archive/...` remapped.
- Technische Dateien wie `.DS_Store` und `index.xlsx` werden nicht als Belegdateien behandelt.

## MyWellness Agent

Ordner:

```text
agent-api/backend/agents/mywellness/
```

Verantwortung:

- Kurse laden
- Kurse vorbereiten
- Kurse buchen
- Buchungen anzeigen
- Logs und Status verwalten
- Health-Daten aus Home Assistant / Withings importieren
- Recovery-Analyse mit LLM
- eigene Health-, Kurs-, Buchungs-, Recovery- und AI-Historie speichern

Datenbank:

```text
agent-api/data/mywellness/mywellness.db
```

Wichtige Services:

- `service.py`
- `health_service.py`
- `ai_service.py`
- `store.py`

Home-Assistant-Bezug:

- MyWellness Health liest Gesundheitsdaten ueber Home Assistant Entities.
- In der Agent Map gibt es deshalb eine Edge `mywellness -> homeassistant`.
- Health-Sync laeuft geplant und schreibt Snapshots sowie geaenderte Kennzahlen in `mywellness.db`.
- Reine Dashboard-GETs sollen read-only bleiben. Kurs- und Health-Historie wird ueber bewusste Agent-Laeufe, Health-Sync, Prepare/Book oder manuelle Aktionen geschrieben.

Historische Tabellen:

- `health_history`
- `health_snapshots`
- `course_history`
- `booking_history`
- `recovery_history`
- `ai_recommendations`

Control:

- `status`
- `start`
- `stop`
- `enable`
- `disable`
- `toggle`
- `run`

Hinweis: `run` kann intern `run_action()` nutzen. Ohne Payload ist der Default im Adapter `prepare`.

## Market Agent

Ordner:

```text
agent-api/backend/agents/market/
```

Verantwortung:

- Watchlist verwalten und Assets per Name, Symbol, ISIN oder WKN aufloesen
- Asset Type automatisch erkennen (`stock`, `etf`, `fund`, `etc`, `crypto`, `index`)
- Kursdaten und kompakte News-/Stimmungsdaten laden
- Watchlist nur bei manuellem Run oder Scheduler-Lauf analysieren
- kompakte Signale `buy`, `hold`, `watch`, `sell` speichern
- Discovery-Ideen erzeugen, ohne die Watchlist zu veraendern
- Signal-Historie mit Timestamp, Signal, Confidence, Risiko und Kurzgrund speichern
- relevante Signalwechsel als Messages erzeugen

Datenbank:

```text
agent-api/data/market/market.db
```

Wichtige Services:

- `agent.py`
- `report_service.py`
- `data_service.py`
- `news_service.py`
- `analysis_service.py`

Control:

- `status`
- `enable`
- `disable`
- `toggle`
- `run`

Hinweis: Market besitzt eine einfache Enabled/Disabled-Konfiguration und wird ueber die Agent Console steuerbar dargestellt.

Market Dashboard ist bewusst kompakt: keine langen News-Texte, keine Marktberichte als Hauptmenue. Reports bleiben im Backend/Archiv abrufbar.

## Vacation Agent

Ordner:

```text
agent-api/backend/agents/vacation/
```

Verantwortung:

- Vacation Mode aus Home Assistant lesen
- Vacation-Status fuer Household/Wall bereitstellen
- `input_boolean.vacation_mode` ueber Vacation Dashboard und Wall Dashboard setzen
- Kalender/CalDAV-Events ueber Home Assistant erkennen
- Urlaubsperioden, Events, Reminder, Presence Profiles und KI-Analysen historisieren
- Reminder regelbasiert erzeugen
- wichtige Vacation-Hinweise als Messages ueber den zentralen Messaging Service schreiben
- Presence Profiles fuer spaetere Anwesenheitssimulation vorbereiten
- Vacation-Analyse mit zentralem LLM-Client erzeugen
- Run-Status, Scheduler-Status und Logs liefern

Datenbank:

```text
agent-api/data/vacation/vacation.db
```

Tabellen:

- `vacation_periods`
- `vacation_events`
- `vacation_reminders`
- `presence_profiles`
- `vacation_ai_analyses`

Konfiguration:

```text
agent-api/backend/agents/vacation/config.yaml
```

Architekturhinweis:

- Vacation Agent und Vacation Mode sind getrennte Konzepte.
- Vacation Agent ist der dauerhaft vorhandene Dienst.
- Vacation Mode ist nur der Hauszustand in Home Assistant: `input_boolean.vacation_mode`.
- Wall Dashboard steuert ausschliesslich Vacation Mode, nicht den Agenten.
- Vacation Dashboard verwaltet Agent Status, Vacation Mode, Urlaub/Kalender, Anwesenheit, Historie und KI-Einschaetzung.
- Der Reminder-Tab wurde aus dem Vacation Dashboard entfernt. Wichtige Hinweise laufen ueber den Messaging Service und das Message Center.
- Es gibt keine automatische Lampen-, Jalousie- oder Geraetesteuerung.
- Die Vacation-KI darf keine Home-Assistant-Aktionen ausfuehren. Sie erzeugt nur Analyse, Empfehlungen, Warnungen und Zusammenfassungen.

Control:

- `status`
- `start`
- `stop`
- `enable`
- `disable`
- `toggle`
- `run`

# Garden Agent

Ordner:

```text
agent-api/backend/agents/garden/
```

Verantwortung:

- Home-Assistant-Entitaeten fuer Gartenkontext automatisch erkennen
- Mähroboter ueber die Domain `lawn_mower` erfassen
- Bodenfeuchte-Sensoren ueber Entity-Namen, Friendly Names und typische Device Classes erkennen
- Bewaesserung ueber `switch`, `valve` oder `input_boolean` mit Garten-/Bewaesserungsbezug erkennen
- Wetter-Entitaeten ueber `weather` erfassen
- Gartenstatus regelbasiert bewerten
- Snapshots historisieren
- Empfehlungen erzeugen, ohne Geraete automatisch zu steuern

Datenbank:

```text
agent-api/data/garden/garden.db
```

Tabelle:

- `garden_snapshots`

Konfiguration:

```text
agent-api/backend/agents/garden/config.yaml
```

Standard-Scheduler:

- Garden Statuspruefung taeglich um 07:00 Uhr

Agent Map:

- `scheduler -> garden`
- `garden -> homeassistant`
- `garden -> database`
- `garden -> openai`

Architekturhinweis:

- Garden ist ein eigener Fachagent, nicht Teil von Household.
- Household bleibt Fassade fuer allgemeinen Haushaltsstatus.
- Garden besitzt die Fachhistorie fuer Garten, Mähroboter, Bodenfeuchte und Bewaesserung.
- Die OpenAI-Kante ist vorbereitet. Aktuell erzeugt der Garden Agent noch keine aktive KI-Analyse.
- Automatische Steuerung von Bewaesserung oder Mähroboter ist bewusst nicht aktiv. Der aktuelle Stand ist advisory/dry-run.
- KI-gestuetzte Empfehlungen sollen erst aktiviert werden, wenn Bodenfeuchte-, Wetter- und Bewaesserungsdaten stabil vorliegen.

Control:

- `status`
- `enable`
- `disable`
- `toggle`
- `run`

# Gemeinsame Services

## HomeAssistantService

Datei:

```text
agent-api/backend/services/homeassistant_service.py
```

Aufgaben:

- Home Assistant REST API lesen
- `/api/states` laden
- einzelne Entity States lesen
- Templates rendern
- Services aufrufen

Config:

```yaml
home_assistant:
  url: HA_URL
  token: HA_TOKEN
```

## WasteService

Datei:

```text
agent-api/backend/services/waste_service.py
```

Aufgaben:

- Abfallstatus aus Home Assistant lesen
- naechste Termine berechnen
- Reminder erzeugen
- bestehende Waste API bedienen

## HouseholdService

Datei:

```text
agent-api/backend/services/household_service.py
```

Rolle:

Zentrale Fassade fuer Haushaltsstatus.

Verwendet:

- `WasteService`
- `HomeAssistantService`
- Vacation Status Provider
- `InfrastructureService`

Liefert:

- `status()`
- `summary()`
- `reminders()`

API:

- `GET /api/household/status`
- `GET /api/household/summary`
- `GET /api/household/reminders`

Es gibt aktuell keine `household.db`.

## InfrastructureService

Datei:

```text
agent-api/backend/services/infrastructure_service.py
```

Rolle:

Zentrale V1-Unterbau-Komponente fuer Netzwerk/FritzBox/Internet-Status aus Home Assistant. InfrastructureService ist ein Backend-Service, kein Agent, besitzt keine Agent-Control-Capabilities und ruft keine Home-Assistant-Services auf.

Signale:

- `internet_status`
- `fritzbox_status`
- `connected_devices`
- `wifi_status`
- `wan_status`
- `upload_speed`
- `download_speed`
- `external_ip`
- `uptime`

Datenbank:

```text
agent-api/data/infrastructure/infrastructure.db
```

Tabellen:

- `infrastructure_events`
- `infrastructure_state`

Config:

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

Wenn keine Entity IDs konfiguriert sind, versucht der Service passende Home-Assistant-Entities automatisch anhand von Namen wie `fritz`, `fritzbox`, `internet`, `wan`, `dsl`, `wifi`, `wlan` und `connected devices` zu entdecken.

Discovery-Regeln:

- Technische Entities wie `Reload`, `Reconnect`, `Restart`, `Neu starten`, `Update` und `Identify` werden ignoriert.
- Es wird nur gelesen, nie geschaltet.
- Home Assistant bleibt alleinige Datenquelle.

Event-Regeln:

- `online -> offline` startet ein offenes `internet_outage` Event mit Severity `critical`.
- `offline -> online` schliesst das Event und berechnet `duration_seconds`.
- `unstable` erzeugt ein Warning-Event.
- `unknown` wird nicht als Ausfall gezaehlt.
- Relevante Events erzeugen menschenlesbare Messages ueber den Messaging Service.

API:

- `GET /api/infrastructure/status`
- `GET /api/infrastructure/summary`
- `GET /api/infrastructure/events`
- `GET /api/infrastructure/events/recent`
- `GET /api/infrastructure/outages`
- `POST /api/infrastructure/check`

Es gibt aktuell keine direkte FritzBox API.

## OrchestratorControlService

Datei:

```text
agent-api/backend/services/orchestrator_control_service.py
```

Rolle:

Zentrale Steuerungsschicht fuer Agent-Control.

Regeln:

- keine agent-spezifischen Imports
- alles ueber Registry und `runtime.service_object`
- keine neue Datenbank
- keine bestehenden Agent APIs ersetzen

## Messaging Service

Ordner:

```text
agent-api/backend/services/messaging/
```

Rolle:

Zentrale Nachrichten- und Hinweis-Infrastruktur fuer Agenten und Systemmeldungen.

Datenbank:

```text
agent-api/data/messaging/messages.db
```

Tabellen:

- `messages`
- `notification_targets`

API:

- `GET /api/messages`
- `GET /api/messages/unread-count`
- `GET /api/messages/source/{source}`
- `POST /api/messages`
- `POST /api/messages/{id}/read`
- `POST /api/messages/read-all`
- `DELETE /api/messages/{id}`
- `DELETE /api/messages`

Architekturregeln:

- Agenten duerfen Messages erzeugen, aber das Message Center ist die zentrale UI fuer Hinweise.
- Vacation Reminder bleiben intern bestehen, wichtige Hinweise werden aber zusaetzlich als menschenlesbare Messages erzeugt.
- Wall Dashboard zeigt eine Glocke und ein Message Center. Bei ungelesenen Nachrichten kann die Glocke dezent animieren; ein Badge ist optional und nicht Teil des Architekturvertrags.
- Push-Architektur ist ueber `notification_targets` vorbereitet, aber automatische Push-Auslieferung ist noch nicht global umgesetzt.

# Home Assistant Integration

Home Assistant ist aktuell Datenquelle fuer:

- Wall Dashboard
- Lights, Covers, Climate, Sensors
- Room/Floor Zuordnung
- Poststatus
- Waste/Abfall
- Vacation Mode
- Vacation Kalender/CalDAV Events
- MyWellness Health
- Infrastructure/Fritzbox

`homeassistant_routes.py` erzeugt weiterhin eine umfassende Wall-Dashboard-Antwort:

- `lights`
- `light_groups`
- `covers`
- `sensors`
- `switches`
- `media_players`
- `climate`
- `temperature_sensors`
- `climate_summary`
- `security`
- `health`
- `agents`
- `post`
- `waste`
- `household`

Aktuelle Verbesserung:

- Sensoren ohne direkte HA-Area-Zuordnung koennen ueber bekannte Raumnamen aus der Floor Map inferiert werden. Dadurch werden z.B. `powder_room_temperature` und `Powder Room` zusammengefuehrt.

# LLM Architektur

LLM-Code liegt unter:

```text
agent-api/backend/services/llm/
```

Komponenten:

- `base.py`
- `factory.py`
- `gemini_client.py`
- `openai_client.py`
- `LlamaLLMClient.py`

Config:

```yaml
llm:
  provider: openai
  openai:
    api_key: OPENAI_API_KEY
    model: gpt-4.1-mini
```

Genutzt wird LLM aktuell vor allem fuer:

- Invoice AI Extraction
- Market Analysis
- MyWellness Health/Recovery Analyse
- Vacation Analyse und Urlaubsvorbereitung

Regeln:

- Agenten nutzen die zentrale LLM-Factory.
- Vacation nutzt keinen eigenen Provider und keine eigene API-Key-Konfiguration.
- Vacation-KI erzeugt keine Steuerbefehle und keine Home-Assistant-Service-Calls.

# Datenbanken

Aktuell verwendete Datenbanken:

```text
agent-api/data/invoices/invoices.db
agent-api/data/infrastructure/infrastructure.db
agent-api/data/market/market.db
agent-api/data/mywellness/mywellness.db
agent-api/data/vacation/vacation.db
agent-api/data/messaging/messages.db
```

Nicht vorhanden:

- `orchestrator.db`
- `household.db`

Architekturregel im aktuellen Stand:

- Agent-Fachdaten bleiben in den jeweiligen Agent-Datenbanken.
- Infrastructure-Events bleiben in `infrastructure.db`.
- Messaging-Nachrichten bleiben in `messages.db`.
- Orchestrator und Household arbeiten aktuell live bzw. ueber bestehende Agent-Services.

# API Struktur

Zentrale APIs:

```text
/api/auth
/api/agents
/api/orchestrator
/api/household
/api/infrastructure
/api/homeassistant
/api/waste
/api/settings
/api/invoices
/api/mywellness
/api/market
/api/vacation
/api/messages
```

Wichtige Orchestrator-Endpunkte:

```text
GET  /api/orchestrator/map
GET  /api/orchestrator/agents/{agent_id}/control
POST /api/orchestrator/agents/{agent_id}/control/{action}
```

Wichtige Agent Discovery:

```text
GET /api/agents
```


# Frontend Multi-App-Struktur

Frontend-Technologie:

- React
- Vite
- TypeScript
- React Flow fuer Agent Map

Struktur:

```text
frontend/src/
├── main.tsx
├── shared/
│   ├── api/
│   ├── auth/
│   ├── components/
│   ├── styles/
│   ├── types/
│   └── utils/
└── apps/
    ├── personal/
    │   ├── main.tsx
    │   ├── App.tsx
    │   ├── pages/
    │   ├── components/
    │   └── routes/
    └── sentero/
        ├── main.tsx
        ├── App.tsx
        ├── pages/
        ├── components/
        ├── routes/
        └── navigation/
```

`frontend/src/main.tsx` waehlt die App ueber `VITE_ROBOTERSTEVE_EDITION`:

- `personal`: bisherige private App mit Agent Console, Invoice, Market, MyWellness, Vacation, Scheduler, Wall Dashboard und Settings.
- `sentero`: eigene Produkt-App mit Premium-/mobile-first UI fuer Setup, Dashboard, Verlauf, Raeume, Kontakte und Einstellungen.

Gemeinsame Bausteine gehoeren nach `src/shared/`. Produktnavigation, Produktseiten und edition-spezifische UI bleiben in `src/apps/<edition>/`. Dadurch muessen spaetere Produkteditionen keine verstreuten Edition-Abfragen in Personal-Komponenten einbauen.

Builds:

```bash
cd agent-api/frontend
npm run build
VITE_ROBOTERSTEVE_EDITION=personal npm run build
VITE_ROBOTERSTEVE_EDITION=sentero npm run build
```

Der Edition Builder setzt `VITE_ROBOTERSTEVE_EDITION` automatisch anhand `frontend_app` der Edition.

# Frontend

Frontend-Technologie:

- React
- TypeScript
- Vite
- Lucide Icons
- React Flow fuer Agent Map

Wichtige Dateien:

```text
agent-api/frontend/src/api/client.ts
agent-api/frontend/src/pages/AgentsPage.tsx
agent-api/frontend/src/components/AgentMap.tsx
agent-api/frontend/src/pages/WallDashboardPage.tsx
agent-api/frontend/src/pages/SettingsPage.tsx
```

## Agent Console

Datei:

```text
agent-api/frontend/src/pages/AgentsPage.tsx
```

Rolle:

- listet Agenten aus `/api/agents`
- liest Runtime-Status und Control-Daten aus `/api/orchestrator/map`
- zeigt Control-Buttons nur fuer `control.supported = true`
- ruft Control-Aktionen ueber `/api/orchestrator/agents/{agent_id}/control/{action}` auf

Wall-Dashboard bleibt read-only und zeigt keine Control-Buttons.

## Agent Map

Datei:

```text
agent-api/frontend/src/components/AgentMap.tsx
```

Rolle:

- nutzt `/api/orchestrator/map`
- rendert Nodes und Edges
- nutzt Manifest-Metadaten aus dem Backend
- enthaelt keine hardcoded Agent-Metadaten fuer Name/Icon/Description

## Wall Dashboard

Datei:

```text
agent-api/frontend/src/pages/WallDashboardPage.tsx
```

Rolle:

- Home Assistant Dashboard fuer Hausstatus
- nutzt `/api/homeassistant/wall`
- zeigt Household- und Infrastructure-Daten
- Fritzbox-Kachel kombiniert Infrastructure-Status mit HA-Entities fuer Upload/Download, IP und Uptime
- bleibt read-only bezogen auf Agent-Control
- Vacation-Kachel steuert ausschliesslich `input_boolean.vacation_mode`
- Glocke/Message Center zeigt zentrale Messages aus `/api/messages`; Badge/Rahmen sind reine UI-Details.

## Settings

Datei:

```text
agent-api/frontend/src/pages/SettingsPage.tsx
```

Rolle:

- zeigt Laufzeit- und Konfigurationsdaten ohne Secret-Werte
- zeigt Agent-Konfiguration, Registry-Aktivierung und API Prefix
- zeigt Household und Infrastructure Integration
- zeigt die zentral konfigurierte Backend-Logdatei aus `config.yaml`
- Settings API gibt den Log-Pfad nur noch als `storage.log_file` zurueck; es gibt keinen zweiten `configured_log_file`-Pfad mehr.

# Deployment Struktur

Relevante Dateien:

```text
agent-api/agent-api.service
agent-api/docs/DEPLOYMENT.md
agent-api/frontend/dist/
```

Backend kann das gebaute Frontend aus `frontend/dist` serven, wenn der Ordner existiert.

Logging:

```text
agent-api/logs/agent-api.log
```

Quelle der Wahrheit:

- `config.yaml` definiert `logging.file`.
- `backend/logging_config.py` loest den Pfad relativ zu `agent-api/` auf.
- `backend/main.py`, agentennahe CLI-Starts und die Settings-Seite verwenden denselben Resolver.
- `/api/settings` zeigt denselben aufgeloesten Pfad in `storage.log_file`.

# Bekannte Architekturhinweise

## Vacation Agent vs Vacation Mode

Vacation Agent und Vacation Mode sind bewusst getrennt:

- Vacation Agent ist ein dauerhaft vorhandener Dienst mit eigener Historie.
- Vacation Mode ist der Home-Assistant-Hauszustand `input_boolean.vacation_mode`.
- Agent-Control startet/stoppt/aktiviert/deaktiviert den Agenten.
- Vacation Mode wird ueber Wall Dashboard und Vacation Dashboard geschaltet.
- Die Aktivierung von Vacation Mode startet keine Geraeteautomation.

## Orchestrator Control ist live, aber ohne Persistenz

Der Orchestrator kann Agenten ueber den Control-Vertrag steuern, speichert aber keine Control-Historie.

Es gibt weiterhin keine:

- `orchestrator.db`
- Run-Historie im Orchestrator
- agentenuebergreifende Event-Tabelle

## Household und Infrastructure sind Services, keine Agenten

Household und Infrastructure sind aktuell bewusst keine klassischen Agenten.

Sie haben:

- eigene Service-Klassen
- eigene API-Router
- keine Manifest-Dateien
- keine Agent-Control-Capabilities
- keine eigene Datenbank

# Aktueller Datenfluss

```text
Frontend Agent Console
  -> /api/agents
  -> /api/orchestrator/map
  -> /api/orchestrator/agents/{id}/control/{action}

Frontend Wall Dashboard
  -> /api/homeassistant/wall
     -> HomeAssistantService
     -> HouseholdService
        -> WasteService
        -> VacationService.status
        -> InfrastructureService
  -> /api/messages
     -> MessagingService

Frontend Settings
  -> /api/settings

Agent Map
  -> Orchestrator Router
     -> Registry Manifests
     -> Agent Runtime Status
     -> Control Capabilities

Vacation Dashboard
  -> /api/vacation/status
  -> /api/vacation/history
  -> /api/vacation/profiles
  -> /api/messages
  -> /api/vacation/ai/analyze
```

# Was aktuell nicht umgesetzt ist

- keine `orchestrator.db`
- keine `household.db`
- keine direkte FritzBox API
- keine Event-Historie fuer Agent-Control
- keine zentralen Start-All/Stop-All-Endpunkte
- keine Control-Buttons im Wall-Dashboard
- keine automatische Anwesenheitssimulation
- keine automatische Lampen-/Jalousie-/Geraetesteuerung durch Vacation
- keine globale automatische Push-Auslieferung ueber Messaging Targets
