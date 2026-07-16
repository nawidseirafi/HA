# Garden Agent

Der Garden Agent ist der Fachagent fuer Gartenautomatisierung in der Personal Edition. Er ist verantwortlich fuer Rasen, Bodenfeuchte, Bewaesserung, Mähroboter und Gartenhistorie.

Home Assistant bleibt die einzige Quelle fuer Sensorzustände und die einzige Schnittstelle zur Gerätesteuerung. KI darf im Garden-Kontext spaeter Empfehlungen liefern, steuert aber keine Geräte direkt.

## Aktueller Stand

Der Agent unterstuetzt eine erste Zone:

- ID: `lawn`
- Name: `Rasen`

Die Zone liest Bodenfeuchte, Bodentemperatur, Batteriestand, optional Soil-Warning, Eve Aqua bzw. ein anderes Bewaesserungsventil, Mähroboter und optional Regen-/Wetterdaten aus Home Assistant.

Die Bewertung erfolgt regelbasiert ueber `GardenDecisionEngine`. Sie erzeugt Status, Entscheidung, empfohlene Dauer, Gruende und Safety-Blocks. Die Engine schaltet niemals selbst Geräte.

Automatik ist standardmaessig aus:

- `garden.control_enabled: false`
- `zones.lawn.irrigation.automatic_enabled: false`

Manuelle Starts laufen trotzdem durch dieselbe Safety-Pruefung. Ein blockierter Zustand ergibt HTTP 409 und kein Home-Assistant-Service-Call.

## Konfiguration

Datei:

```text
backend/agents/garden/config.yaml
```

Minimaler produktiver Ausschnitt:

```yaml
garden:
  enabled: true
  control_enabled: false
  auto_discovery: true

  zones:
    lawn:
      name: Rasen
      entities:
        moisture: "sensor.rasen_soil_moisture"
        temperature: "sensor.rasen_soil_temperature"
        battery: "sensor.rasen_battery"
        soil_warning: "binary_sensor.rasen_soil_warning"
        mower: "lawn_mower.garden_navimow_i208_lidar"
        irrigation: "switch.eve_aqua_123a"
        weather: ""
        rain: ""
      moisture:
        critical_below: 15
        dry_below: 25
        target_min: 35
        wet_above: 60
      temperature:
        irrigation_min_c: 5
        irrigation_max_c: 32
      irrigation:
        enabled: true
        automatic_enabled: false
        default_duration_minutes: 20
        max_duration_minutes: 30
        minimum_pause_hours: 12
        stop_on_sensor_failure: true
      mower:
        enabled: true
        block_during_irrigation: true
        irrigation_block_states:
          - mowing
          - starting
          - returning
      weather:
        enabled: true
        rain_block_enabled: true
        rain_probability_block_above: 60
        forecast_hours: 12
```

Zu ersetzen sind vor allem:

- `sensor.rasen_soil_moisture`
- `sensor.rasen_soil_temperature`
- `sensor.rasen_battery`
- `binary_sensor.rasen_soil_warning`
- `lawn_mower.garden_navimow_i208_lidar`
- `switch.eve_aqua_123a`
- optional `weather.*` oder ein Regen-/Regenwahrscheinlichkeitssensor

Bestehende ältere Garden-Konfigurationen bleiben gueltig. Fehlende Felder werden mit sicheren Defaults normalisiert.

## Entity Discovery

Prioritaet:

1. explizit konfigurierte Entity ID
2. eindeutige Auto-Discovery
3. `unresolved` oder `ambiguous`

Diagnose- und Konfigurationswerte werden nicht fuer die fachliche Entscheidung verwendet. Ignoriert werden insbesondere Namen mit:

- `calibration`
- `calibrate`
- `sampling`
- `interval`
- `configuration`
- `config`
- `sensitivity`
- `diagnostic`
- `linkquality`
- `identify`

Fuer die Bewaesserungsentscheidung werden nur verwendet:

- Bodenfeuchte
- Bodentemperatur
- Batteriestand
- optional Soil-Warning

Kalibrierungs- und Sampling-Entities bleiben reine Diagnosewerte.

## Safety-Regeln

Automatische Bewaesserung wird nur freigegeben, wenn alle relevanten Bedingungen erfuellt sind:

- Garden Agent aktiv
- `control_enabled: true`
- `automatic_enabled: true`
- Bodenfeuchte verfuegbar, numerisch plausibel und nicht veraltet
- Bodenfeuchte unter `dry_below`
- Bodentemperatur im erlaubten Bereich, sofern vorhanden
- Bewaesserungsentity verfuegbar und nicht aktiv
- Mähroboter nicht in blockierendem Zustand
- kein aktiver Regen und keine blockierende Regenwahrscheinlichkeit
- Mindestpause seit letzter Bewaesserung abgelaufen
- kein offener Bewaesserungslauf

Fail-safe: Bei unbekanntem oder widerspruechlichem Zustand erfolgt keine automatische Aktion.

Mähroboter und Bewaesserung sind gegenseitig verriegelt:

- Wenn der Mähroboter mäht, startet oder zurueckkehrt, darf Eve Aqua nicht starten.
- Wenn Eve Aqua aktiv ist oder ein offener Bewaesserungslauf existiert, wird ein Mäherstart durch Garden nicht freigegeben.

## Home-Assistant-Steuerung

Die Steuerung liegt in `GardenIrrigationAdapter` und nutzt ausschliesslich `HomeAssistantService.call_service`.

Unterstuetzte Domains:

- `switch.turn_on` / `switch.turn_off`
- `valve.open_valve` / `valve.close_valve`
- `input_boolean.turn_on` / `input_boolean.turn_off`

Keine Router- oder Frontend-Komponente ruft Home Assistant direkt.

## Persistenz

SQLite:

```text
data/garden/garden.db
```

Bestehende Tabelle:

- `garden_snapshots`

Neue migrationssichere Tabellen:

- `garden_zones`
- `garden_decisions`
- `garden_actions`
- `garden_irrigation_runs`

Entscheidungen, Start-/Stop-Aktionen und Bewaesserungslaeufe werden nachvollziehbar historisiert.

## Scheduler

Der Manifest-Default plant eine taegliche Statuspruefung um 07:00 Uhr.

Garantiertes Ausschalten laeuft ueber einen einmaligen Scheduler-Task. Der Scheduler importiert Garden nicht direkt, sondern ruft generisch Agent-Control `garden/run` mit Payload auf:

```json
{
  "action": "irrigation_stop",
  "zone_id": "lawn",
  "source": "scheduler"
}
```

Zusaetzlich prueft jeder Garden-Statuslauf, ob ein offener Bewaesserungslauf ueberfaellig ist.

## API

Bestehende Endpunkte bleiben erhalten:

- `GET /api/garden/status`
- `GET /api/garden/config`
- `PUT /api/garden/settings`
- `POST /api/garden/enable`
- `POST /api/garden/disable`
- `POST /api/garden/toggle`
- `POST /api/garden/run`
- `GET /api/garden/history`
- `GET /api/garden/snapshot/latest`

Neue Zonen-Endpunkte:

- `GET /api/garden/zones`
- `GET /api/garden/zones/{zone_id}`
- `POST /api/garden/evaluate`
- `POST /api/garden/zones/{zone_id}/evaluate`
- `POST /api/garden/zones/{zone_id}/irrigation/start`
- `POST /api/garden/zones/{zone_id}/irrigation/stop`
- `GET /api/garden/zones/{zone_id}/decisions`
- `GET /api/garden/zones/{zone_id}/irrigation-runs`

Manueller Start:

```json
{
  "duration_minutes": 15
}
```

Statuscodes:

- `404`: unbekannte Zone
- `409`: Safety-Block oder widerspruechlicher Zustand
- `422`: ungueltige Dauer oder Payload

## Frontend

Die Personal-App besitzt ein Garden Dashboard unter:

```text
/garden
```

Die Hauptansicht zeigt keine Entity IDs. Entity IDs stehen nur im Diagnosebereich der Zone.

## Messaging

Messages werden nur fuer handlungsrelevante Ereignisse erzeugt, zum Beispiel:

- Home-Assistant-Service-Call fehlgeschlagen
- Bewaesserung konnte nicht beendet werden
- maximale Laufzeit ueberschritten
- kritischer Sensor-/Geraetezustand

Routine-Evaluationen erzeugen keine Message-Center-Nachrichten.
