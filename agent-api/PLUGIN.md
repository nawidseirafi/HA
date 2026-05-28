# Agent Plugin Contract

Ein Agent wird als Ordner unter `agent-api/backend/agents/<id>/` angelegt.

Minimaler Aufbau:

```text
backend/agents/example/
  manifest.yaml
  routes.py
  service.py
```

`manifest.yaml`:

```yaml
id: example
name: Example Agent
description: Kurzbeschreibung fuer die Agenten-Uebersicht.
enabled: true
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

`routes.py` muss einen FastAPI-`router` exportieren. Wenn `runtime.service_object`
gesetzt ist und dieses Objekt `start_scheduler()` / `stop_scheduler()` besitzt,
ruft die API diese Methoden beim Starten und Stoppen automatisch auf.

Bekannte UI-Icons im Frontend: `Bot`, `FileText`, `Dumbbell`, `LineChart`,
`Mail`, `CalendarCheck`, `Home`, `Settings2`.

Ein `dashboard_route` ist optional. Ohne eigene Frontend-Route erscheint der
Agent in der Uebersicht als installiert, aber ohne oeffnende Detailseite.
