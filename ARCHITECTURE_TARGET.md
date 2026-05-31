# Empfohlene Zielarchitektur

Ziel ist eine kontrollierte Weiterentwicklung der bestehenden Architektur, ohne die aktuellen Agenten, Datenbanken oder API-Konzepte zu zerstören.

Der wichtigste Grundsatz: Die vorhandene Registry bleibt Discovery-Schicht. Der Orchestrator wird schrittweise zu einer Status- und Koordinationsschicht ausgebaut, aber erst nachdem der aktuelle Zustand sauber dokumentiert und stabilisiert ist.

# Leitlinien

- Keine bestehenden Agenten verschieben.
- Keine bestehenden Datenbanken ersetzen.
- Keine bestehenden API-Endpunkte brechen.
- Manifeste bleiben Quelle für Agent-Metadaten.
- Agenten behalten ihre Domänen-Datenbanken.
- Neue Querschnittsdaten bekommen eigene Datenbanken.
- Orchestrator koordiniert, aber besitzt keine Fachlogik der Agenten.

# Minimale Änderungen

Empfohlene Minimalroute:

1. Registry als Manifest-Discovery beibehalten.
2. Orchestrator-API nicht ersetzen, sondern erweitern.
3. Agent-Statusmodell vereinheitlichen.
4. Household-Themen aus `homeassistant_routes.py` und `waste_service.py` schrittweise in einen Household Service kapseln.
5. Neue Persistenz nur für neue Querschnittsfunktionen anlegen:
   - `household.db`
   - `orchestrator.db`
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

# FritzBox / Infrastructure Monitoring

FritzBox und Infrastruktur sollten als eigene Datenquelle modelliert werden, nicht direkt in bestehende Agenten eingebaut.

Minimaler Einstieg:

- Neuer Service `backend/services/infrastructure_service.py`
- Status zunächst live berechnen, später optional in `household.db` oder `orchestrator.db` persistieren.
- Mögliche Signale:
  - Internet erreichbar
  - FritzBox erreichbar
  - WAN/IP-Status
  - WLAN/Gästenetz Status
  - wichtige Geräte online/offline
  - Latenz/Fehlerstatus

Integration:

- Wall-Dashboard zeigt Infrastruktur-Karte.
- Orchestrator Map bekommt Service Node `infrastructure` oder `fritzbox`.
- Household Service kann Infrastrukturwarnungen als Household Events übernehmen.

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
- `paused`: bewusst pausiert oder idle bei aktivem Agent
- `disabled`: deaktiviert
- `error`: Fehlerzustand

Wichtig:

- Name, Icon und Description kommen aus Manifesten.
- Runtime-Status kommt aus Agent-Services.
- UI sollte nicht eigene Agent-Metadaten hardcoden.

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
│   ├── household_service.py        # neu, später
│   ├── infrastructure_service.py   # neu, später
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
4. Household Service als Fassade über Waste/Vacation/HA-Kontext einführen.
5. Erst danach `household.db` anlegen.
6. Erst danach `orchestrator.db` anlegen.
7. Infrastruktur/FritzBox als separaten Service ergänzen.

# Empfohlene nächste Schritte

## P1

- Agent-Statusmodell schriftlich festlegen: `active`, `running`, `paused`, `disabled`, `error`.
- `/api/orchestrator/map` zur einzigen Quelle für Agent-Map-Status im Frontend machen.
- Alle Agent-Metadaten im Frontend aus Manifesten beziehen.
- Prüfen, ob MyWellness `idle` als `paused` oder `active` dargestellt werden soll. Fachlich wirkt `enabled + idle` eher wie `active`, während `disabled` orange/grau sein sollte.
- Secrets aus `agent-api.service` entfernen und konsequent über Environment-Datei laden.

## P2

- `HouseholdService` als Fassade einführen, ohne `WasteService` zu löschen.
- Wall-Dashboard schrittweise auf `HouseholdService.summary()` umstellen.
- Datenmodell für `household.db` finalisieren, aber erst nach stabiler Service-Fassade anlegen.
- Orchestrator-Status-Events entwerfen, aber noch nicht breit in Agenten einbauen.

## P3

- `orchestrator.db` einführen, wenn Statusmodell und Map stabil sind.
- FritzBox-/Infrastructure-Service ergänzen.
- Agent-Abhängigkeiten für Map und Scheduling modellieren.
- LLM-Factory bereinigen: Claude-Pfad entweder implementieren oder aus der Konfiguration entfernen.
- Langfristig ältere und neue Home-Assistant-Clients konsolidieren.

