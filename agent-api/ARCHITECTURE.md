# RoboterSteve Architektur README - Ist-Zustand

Stand: 2026-06-01

Dieses Dokument beschreibt den aktuellen Zustand des Projekts nach P1, P2, Infrastructure Monitoring und P2.5 Agent-Control. Es ist keine Zielarchitektur und keine Umbauanleitung, sondern eine technische Bestandsaufnahme des laufenden Systems.

# Systemuebersicht

RoboterSteve besteht aktuell aus einer FastAPI-Backend-Anwendung und einem React/Vite-Frontend unter `agent-api/`.

Der Backend-Einstieg ist:

```text
agent-api/backend/main.py
```

Das Backend bindet zentrale Router ein:

- Auth
- Agents
- Orchestrator
- Household
- Infrastructure
- Home Assistant Wall API
- Waste
- Settings
- dynamisch geladene Agent-Router aus Manifesten

Das Frontend liegt unter:

```text
agent-api/frontend/
```

Wichtige UI-Bereiche:

- Agent Console
- Agent Map
- Wall Dashboard
- Settings
- Invoice Dashboard
- MyWellness Dashboard
- Market Dashboard

# Ordnerstruktur

```text
agent-api/
├── backend/
│   ├── agents/
│   │   ├── control.py
│   │   ├── registry.py
│   │   ├── routes.py
│   │   ├── invoices/
│   │   ├── market/
│   │   ├── mywellness/
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
│   │   ├── orchestrator_control_service.py
│   │   ├── settings_service.py
│   │   ├── waste_service.py
│   │   ├── core/ha_client.py
│   │   └── llm/
│   ├── config.py
│   ├── main.py
│   └── paths.py
├── data/
│   ├── invoices/
│   ├── market/
│   └── mywellness/
├── frontend/
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

- `backend/agents/*/manifest.yaml` entdecken
- Manifestdaten in `AgentManifest` laden
- sichere Metadaten per `public_dict()` bereitstellen
- aktivierte Agent-Router dynamisch einbinden
- Runtime-Service-Objekte finden
- Agent-Control-Adapter per `get_agent_control(agent_id)` bereitstellen

Aktuell gilt:

- `enabled: false` im Manifest verhindert das automatische Einbinden des Agent-Routers ueber `include_agent_routers(app)`.
- `get_agent_control(agent_id)` kann dennoch ein Service-Objekt ueber `runtime.service_object` finden, wenn `route_module` importierbar ist.
- Die Registry speichert keinen Runtime-State und nutzt keine eigene Datenbank.

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

Statuswerte:

- `active`
- `running`
- `paused`
- `disabled`
- `error`

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

Aktuell erkannte Capabilities:

```text
invoices:    status, start, stop, enable, disable, toggle, run
market:      run
mywellness:  status, start, stop, enable, disable, toggle, run
vacation:    status, run
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

- Watchlist verwalten
- Kursdaten laden
- News laden
- Marktberichte erzeugen
- Signale speichern

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

- `run`

Hinweis: `enable`/`disable` sind aktuell nicht als Agent-Control implementiert und liefern ueber den Orchestrator sauber `405 unsupported`.

## Vacation Agent

Ordner:

```text
agent-api/backend/agents/vacation/
```

Verantwortung:

- Vacation Mode aus Home Assistant lesen
- Vacation-Status fuer Household/Wall bereitstellen
- Run-Status und Logs liefern

Konfiguration:

```text
agent-api/backend/agents/vacation/config.yaml
```

Aktueller Architekturhinweis:

- `vacation/config.yaml` enthaelt `enabled: true`.
- `vacation/manifest.yaml` enthaelt aktuell `enabled: false`.
- Dadurch ist Vacation als Runtime-Konzept vorhanden, wird aber ueber die Manifest-Registry nicht wie ein aktivierter Agent-Router eingebunden.
- Der Orchestrator und Household koennen den Service trotzdem direkt als Datenquelle nutzen, weil `orchestrator_routes.py` und `household_routes.py` ihn importieren.

Control:

- `status`
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

Live-Status fuer Netzwerk/Fritzbox/Infrastruktur aus Home Assistant.

Signale:

- `internet_status`
- `fritzbox_status`
- `connected_devices`
- `wifi_status`

Config:

```yaml
infrastructure:
  entities:
    internet_status: ""
    fritzbox_status: ""
    connected_devices: ""
    wifi_status: ""
```

Wenn keine Entity IDs konfiguriert sind, versucht der Service passende Home-Assistant-Entities automatisch anhand von Namen wie `fritz`, `fritzbox`, `internet`, `wan`, `dsl`, `wifi`, `wlan` und `connected devices` zu entdecken.

API:

- `GET /api/infrastructure/status`
- `GET /api/infrastructure/summary`

Es gibt aktuell keine direkte FritzBox API und keine Infrastructure-Datenbank.

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

# Home Assistant Integration

Home Assistant ist aktuell Datenquelle fuer:

- Wall Dashboard
- Lights, Covers, Climate, Sensors
- Room/Floor Zuordnung
- Poststatus
- Waste/Abfall
- Vacation Mode
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

# Datenbanken

Aktuell verwendete Datenbanken:

```text
agent-api/data/invoices/invoices.db
agent-api/data/market/market.db
agent-api/data/mywellness/mywellness.db
```

Nicht vorhanden:

- `orchestrator.db`
- `household.db`
- `infrastructure.db`

Architekturregel im aktuellen Stand:

- Agent-Fachdaten bleiben in den jeweiligen Agent-Datenbanken.
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

## Settings

Datei:

```text
agent-api/frontend/src/pages/SettingsPage.tsx
```

Rolle:

- zeigt Laufzeit- und Konfigurationsdaten ohne Secret-Werte
- zeigt Agent-Konfiguration, Registry-Aktivierung und API Prefix
- zeigt Household und Infrastructure Integration
- zeigt tatsaechliche Backend-Logdatei und konfigurierte Logdatei

# Deployment Struktur

Relevante Dateien:

```text
agent-api/agent-api.service
agent-api/DEPLOYMENT.md
agent-api/frontend/dist/
```

Backend kann das gebaute Frontend aus `frontend/dist` serven, wenn der Ordner existiert.

Logging:

```text
agent-api/logs/agent-api.log
```

Hinweis:

- `config.yaml` enthaelt aktuell einen konfigurierten Logging-Pfad `../logs/orchstrator.log`, der nicht der tatsaechlich in `main.py` verwendeten Datei entspricht.

# Bekannte Architekturhinweise

## Vacation Manifest vs Config

Aktuelle Abweichung:

- `backend/agents/vacation/config.yaml`: `enabled: true`
- `backend/agents/vacation/manifest.yaml`: `enabled: false`

Auswirkung:

- Settings kann Vacation als Runtime-Config aktiv anzeigen.
- Registry betrachtet Vacation im Manifest als deaktiviert.
- Orchestrator/Household nutzen Vacation trotzdem als importierte Statusquelle.

Diese Abweichung sollte bewusst entschieden werden: entweder Manifest aktivieren oder Vacation als bewusst read-only/experimentell dokumentieren.

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

Frontend Settings
  -> /api/settings

Agent Map
  -> Orchestrator Router
     -> Registry Manifests
     -> Agent Runtime Status
     -> Control Capabilities
```

# Was aktuell nicht umgesetzt ist

- keine `orchestrator.db`
- keine `household.db`
- keine direkte FritzBox API
- keine Event-Historie fuer Agent-Control
- keine zentralen Start-All/Stop-All-Endpunkte
- keine Control-Buttons im Wall-Dashboard
- keine Persistenz fuer Infrastructure-Verlauf

