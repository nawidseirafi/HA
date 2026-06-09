# Empfohlene Zielarchitektur

Ziel ist eine kontrollierte Weiterentwicklung der bestehenden Architektur, ohne die aktuellen Agenten, Datenbanken oder API-Konzepte zu zerstören.

Der wichtigste Grundsatz: Die vorhandene Registry bleibt Discovery-Schicht. Der Orchestrator wird schrittweise zu einer Status- und Koordinationsschicht ausgebaut, aber erst nachdem der aktuelle Zustand sauber dokumentiert und stabilisiert ist.

# Leitlinien

- Keine bestehenden Agenten verschieben.
- Keine neuen Repos fuer Produkteditionen anlegen; Editionen bleiben YAML-gesteuerte Zuschnitte im gemeinsamen Repo.
- Keine bestehenden Datenbanken ersetzen.
- Keine bestehenden API-Endpunkte brechen.
- Manifeste bleiben Quelle für Agent-Metadaten.
- Agenten behalten ihre Domänen-Datenbanken.
- Neue Querschnittsdaten bekommen eigene Datenbanken.
- Orchestrator koordiniert, aber besitzt keine Fachlogik der Agenten.
- Orchestrator darf Agenten zentral starten und stoppen, aber nur über einen einheitlichen Agent-Control-Vertrag.
- Hinweise, Warnungen und Aufgaben laufen zentral über den Messaging Service.
- Fachliche Historien bleiben bei den owning Agents.

# Minimale Änderungen

Empfohlene Minimalroute:

1. Registry als Manifest-Discovery beibehalten.
2. Orchestrator-API nicht ersetzen, sondern erweitern.
3. Agent-Statusmodell vereinheitlichen.
4. Household-Themen aus `homeassistant_routes.py` und `waste_service.py` schrittweise in einen Household Service kapseln.
5. Neue Persistenz nur für neue Querschnittsfunktionen anlegen:
   - `messaging/messages.db` ist umgesetzt.
   - `infrastructure/infrastructure.db` ist umgesetzt.
   - `household.db` und `orchestrator.db` bleiben optionale spätere Schritte.
6. Frontend Agent Map weiter gegen ein stabiles `/api/orchestrator/map`-Datenmodell bauen.

# Household Service Integration

Aktuell sind Household-Funktionen verteilt:

- Waste: `backend/services/waste_service.py`
- Wall-Dashboard: `backend/api/homeassistant_routes.py`
- Vacation Mode: `backend/agents/vacation/service.py`
- Briefkasten-Kontext: `input_boolean.post_im_briefkasten`
- Home Assistant Geräte-/Entity-Zustände: `HomeAssistantService`

Ziel:

- Neuer `backend/services/household_service.py` oder später ein Agent `backend/agents/household/`.
- Start als Service ist risikoärmer als sofortiger Agent-Umbau.
- Verantwortlich für:
  - Abfallstatus und Erinnerungen
  - Briefkastenstatus
  - Vacation Mode Kontext
  - einfache Haushaltsereignisse
  - optionale FritzBox-/Infrastructure-Statussignale
  - Wall-kompatible Zusammenfassungen

Minimale Integration:

- `WasteService` nicht löschen.
- `HouseholdService` kann `WasteService` intern verwenden.
- `homeassistant_routes.py` ruft mittelfristig `HouseholdService.summary()` auf.
- `vacation` bleibt zunächst eigener Agent, kann aber als Datenquelle in Household einfließen.

# Messaging Service

Status: umgesetzt.

Der zentrale Messaging Service ist die Querschnittskomponente fuer Hinweise, Warnungen, Aufgaben und spaeter Push-Ziele.

```text
backend/services/messaging/
data/messaging/messages.db
```

Tabellen:

- `messages`
- `notification_targets`

Regeln:

- Agenten erzeugen fachliche Messages ueber `MessagingService.create_message()`.
- Frontend-Hinweise sollen bevorzugt aus `/api/messages` kommen.
- Wall Dashboard zeigt Glocke und Message Center. Bei ungelesenen Nachrichten kann die Glocke dezent animieren; Badge/Rahmen sind optionale UI-Details.
- Vacation Reminder bleiben intern, wichtige Vacation-Hinweise erscheinen als Messages.
- `notification_targets` bereitet spaetere Push-Auslieferung vor; warning/critical sollen spaeter push-faehig sein.

# household.db

Nicht sofort anlegen. Empfohlenes Zielmodell:

```text
data/household/household.db
```

Mögliche Tabellen:

- `household_events`
  - `id`
  - `event_type`
  - `severity`
  - `title`
  - `message`
  - `source`
  - `entity_id`
  - `payload_json`
  - `created_at`
  - `resolved_at`
- `household_state`
  - `key`
  - `value_json`
  - `updated_at`
- `household_reminders`
  - `id`
  - `reminder_type`
  - `title`
  - `message`
  - `due_at`
  - `status`
  - `created_at`
  - `updated_at`

Zweck:

- Verlauf und aktuelle Haushaltszustände getrennt von Agent-Fachdaten speichern.
- Wall-Dashboard nicht nur live aus Home Assistant berechnen müssen.
- Erinnerungen nachvollziehbar machen.

# orchestrator.db

Nicht sofort anlegen. Empfohlenes Zielmodell:

```text
data/orchestrator/orchestrator.db
```

Mögliche Tabellen:

- `agent_registry_snapshot`
  - Manifest-Snapshot für UI/Debugging
- `agent_status_events`
  - historisierte Statuswechsel pro Agent
- `agent_runs`
  - agentenübergreifende Run-Metadaten
- `orchestrator_events`
  - Entscheidungen, Fehler, Koordinationsereignisse
- `agent_dependencies`
  - optionale Beziehungen für Agent Map und Scheduling

Wichtig:

- Bestehende Agent-Daten bleiben in `invoices.db`, `mywellness.db`, `market.db`.
- `orchestrator.db` speichert Querschnittsstatus, nicht Rechnungen, Kurse oder Marktberichte.

# Scheduler Agent

Status: Version 1.0 umgesetzt.

Der Scheduler Agent ist die zentrale Zeitsteuerung der Plattform. Er ersetzt bestehende Agent-Scheduler noch nicht hart, sondern stellt den gemeinsamen Scheduler-Vertrag bereit und migriert geplante Laeufe schrittweise in eine zentrale Steuerung.

Ziel:

- Agent-Runs zentral planen
- `last_run` und `next_run` pro Job speichern
- Run-Status sichtbar machen
- Jobs fuer Infrastructure, Vacation, MyWellness, Market und Invoice verwalten
- einmalige und geplante Laeufe einheitlich beschreiben

Wichtige Regeln:

- Bestehende Agent-Scheduler werden nicht gebrochen.
- Agenten behalten bis zur Migration ihre bestehenden `start_scheduler()` / `stop_scheduler()` Implementierungen.
- Der Orchestrator nutzt den Scheduler spaeter nur koordinierend.
- Der Scheduler fuehrt Agenten ueber den Agent-Control-Vertrag aus, nicht ueber agent-spezifische Imports.
- Fachliche Daten bleiben in den jeweiligen Agent-/Service-Datenbanken.

Umgesetztes Modul:

```text
backend/agents/scheduler/service.py
backend/agents/scheduler/store.py
backend/agents/scheduler/routes.py
data/scheduler/scheduler.db
```

Tabellen:

- `scheduler_tasks`
- `scheduler_runs`

Standard-Tasks:

- Market Analyse um 06:00, 12:00 und 18:00
- Infrastructure Health Check alle 5 Minuten
- Vacation Statuspruefung taeglich
- Household Fensterpruefung um 22:00
- Invoice Agent Lauf um 22:00
- MyWellness Prepare um 17:00 und Book um 20:59

Agenten deklarieren empfohlene Scheduler-Defaults optional im eigenen `manifest.yaml`. Der Scheduler legt fehlende Tasks automatisch an, ueberschreibt aber keine bestehenden lokalen Anpassungen.

Weiterhin offen fuer spaetere Versionen:

- Task-Abhaengigkeiten
- Task-Ketten und Task-Gruppen
- Kalender-Integration
- vollstaendige Migration aller bestehenden Agent-internen Scheduler

# Agent-Domaenenhistorien

Bereits umgesetzt bzw. Zielregel:

- MyWellness speichert Health-, Kurs-, Buchungs-, Recovery- und AI-Historien in `data/mywellness/mywellness.db`.
- Vacation speichert Urlaubsperioden, Events, Reminder, Presence Profiles und KI-Analysen in `data/vacation/vacation.db`.
- Messaging speichert Querschnittsnachrichten in `data/messaging/messages.db`.
- Orchestrator besitzt diese Fachdaten nicht.
- Household darf Vacation/MyWellness/Messaging-Daten konsumieren, aber nicht besitzen.

# FritzBox / Infrastructure Monitoring

FritzBox und Infrastruktur sind als eigene Unterbau-Komponente umgesetzt und werden nicht direkt in bestehende Agenten eingebaut.

Status: Infrastructure Service V1 umgesetzt.

Dateien:

```text
backend/services/infrastructure_service.py
backend/services/infrastructure_store.py
backend/api/infrastructure_routes.py
data/infrastructure/infrastructure.db
```

Signale:

- Internet erreichbar
- FritzBox erreichbar
- WAN/IP-Status
- WLAN Status
- verbundene Geräte
- Upload/Download
- externe IP
- Uptime

Regeln:

- Home Assistant bleibt Datenquelle.
- Keine direkte FritzBox API.
- Keine Home-Assistant-Service-Calls.
- Infrastructure ist kein Agent und besitzt keine Agent-Control-Capabilities.
- Statuswechsel werden in `infrastructure_events` historisiert.
- Der aktuelle Zustand wird in `infrastructure_state` gespeichert.
- Relevante warning/critical Ereignisse erzeugen Messages ueber den Messaging Service.

Integration:

- Wall-Dashboard zeigt Infrastruktur-Karte.
- Household Service konsumiert `InfrastructureService.summary()`, besitzt aber keine Infrastructure-Events.
- System/Settings zeigt kompakte Livewerte.
- Orchestrator Map kann spaeter optional einen Service Node `infrastructure` bekommen.

# Agent Map Datenmodell

`/api/orchestrator/map` sollte ein stabiler Vertrag bleiben.

Empfohlenes Zielmodell:

```json
{
  "updated_at": "2026-05-31T12:00:00",
  "summary": {
    "active": 2,
    "paused": 1,
    "errors": 0,
    "last_activity": "...",
    "next_activity": "..."
  },
  "nodes": [
    {
      "id": "mywellness",
      "label": "MyWellness-Agent",
      "subtitle": "Kurse finden...",
      "kind": "agent",
      "status": "active",
      "icon": "Heart",
      "enabled": true,
      "dashboard_route": "mywellnessDashboard",
      "last_run": "...",
      "next_action": "...",
      "source": "manifest+runtime"
    }
  ],
  "edges": [
    {
      "id": "orchestrator-mywellness",
      "from": "orchestrator",
      "to": "mywellness",
      "kind": "primary",
      "active": true,
      "status": "active"
    }
  ]
}
```

Statuswerte sollten einheitlich bleiben:

- `active`: aktiviert und bereit
- `running`: führt gerade Arbeit aus
- `disabled`: deaktiviert
- `error`: Fehlerzustand

`paused` bleibt optional fuer spaetere Pause/Resume-Semantik, ist aber kein Basisstatus fuer die aktuellen Agenten.

Wichtig:

- Name, Icon und Description kommen aus Manifesten.
- Runtime-Status kommt ueber den generischen Agent-Control-Vertrag aus Agent-Services.
- UI sollte nicht eigene Agent-Metadaten hardcoden.

# Agent Control Contract

Ziel: Der Orchestrator soll alle Agenten zentral starten, stoppen und später optional pausieren können, ohne Fachlogik der Agenten zu übernehmen.

Jeder Agent mit `runtime.service_object` sollte folgende Methoden unterstützen:

- `status() -> dict`
- `enable() -> dict`
- `disable() -> dict`
- `start_scheduler() -> None`
- `stop_scheduler() -> None`
- optional `run(...) -> dict`
- optional `pause() -> dict` und `resume() -> dict`

Semantik:

- `start_scheduler()` startet nur geplante Hintergrundläufe.
- `stop_scheduler()` stoppt nur geplante Hintergrundläufe und löscht keine Fachdaten.
- Spaeter kann ein zentraler Scheduler diese Verantwortung uebernehmen; bis dahin bleiben bestehende Agent-Scheduler gueltig.
- `enable()` aktiviert den Agenten als Laufzeit-/Planungszustand.
- `disable()` deaktiviert den Agenten als Laufzeit-/Planungszustand, ohne APIs zu entfernen.
- Start/Stop/Enable/Disable müssen idempotent sein.
- Statuswerte müssen mindestens auf `active`, `running`, `disabled`, `error` normalisierbar sein.
- `paused` ist optional fuer spaetere Pause/Resume-Funktionen.

Bestehende Orchestrator-API:

- `GET /api/orchestrator/agents/{agent_id}/control`
- `POST /api/orchestrator/agents/{agent_id}/control/{action}`

Optionale spaetere Bulk-Endpunkte:

- `POST /api/orchestrator/agents/start-all`
- `POST /api/orchestrator/agents/stop-all`

Wichtig:

- Bestehende Agent-Endpunkte bleiben erhalten.
- Orchestrator ruft nur den Control-Vertrag auf.
- Agenten besitzen weiterhin ihre Fachlogik, Datenbanken und Konfiguration.
- Agent-Metadaten kommen weiterhin aus `manifest.yaml`.

# Vacation Agent Zielbild

Status Version 1.5:

- Vacation Agent ist ein eigener Agent mit Dashboard und eigener DB.
- Vacation Mode ist getrennt und bleibt `input_boolean.vacation_mode`.
- Kalender/CalDAV wird ueber Home Assistant gelesen.
- Reminder werden regelbasiert erzeugt.
- Wichtige Hinweise werden als Messages erzeugt.
- KI ist reine Analyse- und Empfehlungsschicht.
- Keine KI- oder Agent-Komponente darf Geraete steuern.

Nicht Bestandteil von Version 1.5:

- automatische Anwesenheitssimulation
- Lichtsteuerung
- Jalousiesteuerung
- automatische Smart-Home-Regeln

Version 2.0 kann auf den vorhandenen Presence Profiles aufbauen, muss aber eine separate regelbasierte Simulation Engine bekommen.

# MyWellness Zielbild

Status:

- Health-Historie und Snapshots sind Teil von `mywellness.db`.
- Recovery-Analysen und KI-Empfehlungen werden historisiert.
- Trend- und History-Daten werden fuer spaetere KI-Kontexte vorbereitet.
- Dashboard-GETs sollen read-only bleiben.
- Schreibende Aktionen sind Health-Sync, Prepare/Book, Settings, Buchung/Stornierung und explizite Imports.

Zielregel:

- MyWellness ersetzt Home Assistant nicht.
- Home Assistant bleibt Datenquelle.
- MyWellness besitzt langfristige Health- und Trainingshistorie.
- KI interpretiert Trends, ruft aber keine Smart-Home-Aktionen aus.

# Empfohlene Zielmodule

Minimal und kompatibel:

```text
backend/
├── agents/
│   ├── registry.py
│   ├── invoices/
│   ├── market/
│   ├── mywellness/
│   └── vacation/
├── services/
│   ├── household_service.py        # umgesetzt als Fassade, ohne household.db
│   ├── infrastructure_service.py   # umgesetzt
│   ├── infrastructure_store.py     # umgesetzt
│   ├── messaging/                  # umgesetzt
│   ├── orchestrator_store.py       # neu, später
│   └── ...
└── api/
    ├── orchestrator_routes.py      # erweitern
    ├── homeassistant_routes.py     # langfristig schlanker machen
    └── ...
```

# Kontrollierter Migrationspfad

1. Ist-Zustand stabilisieren.
2. Statusmodell vereinheitlichen.
3. Orchestrator Map als alleinige UI-Quelle für Agent-Status verwenden.
4. Messaging Service als zentrale Hinweis-/Message-Schicht verwenden.
5. Household Service als Fassade über Waste/Vacation/HA-Kontext weiter stabilisieren.
6. Infrastructure Service V1 als zentrale Netzwerk-/FritzBox-Schicht nutzen.
7. Scheduler Agent/Service V1 als zentrale Zeitsteuerung nutzen; Manifest-Defaults nur als Initialwerte behandeln.
8. Erst danach bei Bedarf `household.db` anlegen.
9. Erst danach `orchestrator.db` anlegen.

# Empfohlene nächste Schritte

## P1

- Agent-Statusmodell schriftlich festlegen: `active`, `running`, `paused`, `disabled`, `error`.
- `/api/orchestrator/map` zur einzigen Quelle für Agent-Map-Status im Frontend machen.
- Alle Agent-Metadaten im Frontend aus Manifesten beziehen.
- Frontend-Produkteditionen als getrennte Apps unter `frontend/src/apps/<edition>/` fuehren, nicht ueber verstreute Edition-Abfragen in Komponenten.
- MyWellness `enabled + nicht laufend` wird als `active` dargestellt.
- Secrets aus `agent-api.service` entfernen und konsequent über Environment-Datei laden.
- Dashboard-GETs read-only halten. Schreibende Datenimporte nur ueber explizite Aktionen oder Scheduler.

## P2

- `HouseholdService` als Fassade einführen, ohne `WasteService` zu löschen.
- Wall-Dashboard schrittweise auf `HouseholdService.summary()` umstellen.
- Datenmodell für `household.db` finalisieren, aber erst nach stabiler Service-Fassade anlegen.
- Orchestrator-Status-Events entwerfen, aber noch nicht breit in Agenten einbauen.
- Agent-Control-Vertrag für `enable`, `disable`, `start_scheduler`, `stop_scheduler` dokumentieren und bestehende Agenten dagegen prüfen.
- Messaging Push-Ziele fertigstellen und warning/critical optional automatisch ausliefern.

## P3

- `orchestrator.db` einführen, wenn Statusmodell und Map stabil sind.
- Zentrale Orchestrator-Start/Stop-Endpunkte für einzelne Agenten und alle Agenten implementieren.
- Scheduler schrittweise als Quelle der Wahrheit fuer aktive Laufzeiten ausbauen; bestehende Agent-Defaults duerfen Scheduler-Tasks nicht ueberschreiben.
- Infrastructure Service um weitere stabile HA-Signale, Aggregationen und Push-Ziele erweitern.
- Agent-Abhängigkeiten für Map und Scheduling modellieren.
- LLM-Factory bereinigen: Claude-Pfad entweder implementieren oder aus der Konfiguration entfernen.
- Langfristig ältere und neue Home-Assistant-Clients konsolidieren.
- Vacation Presence Simulation Engine als Version 2.0 separat entwerfen.


# Editionen als Zielstandard

Editionen sind der empfohlene Weg fuer unterschiedliche Deployments aus demselben Repository.

Zielregeln:

- Editionen werden in `agent-api/editions/*.yaml` beschrieben.
- Runtime-Auswahl erfolgt ueber `ROBOTERSTEVE_EDITION`, danach `config.yaml -> edition.name`, danach `personal`.
- Registry, Router, Runtime-Services, Scheduler-Manifest-Tasks und Orchestrator Map respektieren die aktive Edition.
- `personal` bleibt die private Vollinstallation.
- `seniorcare` bleibt eine Produktedition mit Core, Scheduler und Senior-Agent.
- Neue Produkteditionen bekommen eigene Frontend-Apps unter `frontend/src/apps/<edition>/`.
- Gemeinsame UI-/API-/Auth-/Style-Bausteine gehoeren nach `frontend/src/shared/`.
- `tools/build_edition.py` ist der Standardpfad fuer saubere Deployment-Artefakte ohne private Daten.
- Produkt-Builds muessen per `editions/edition.lock` strikt auf ihre Edition festgelegt sein; kein stiller Fallback von SeniorCare auf Personal.

Nicht-Ziele:

- Kein neues Repo pro Edition.
- Keine Kopie der gesamten Personal-App fuer jedes Produkt.
- Keine privaten Daten, Logs oder Secrets in Edition-Builds.
- Keine UI-Logik, die ueberall `if edition === ...` verteilt.
