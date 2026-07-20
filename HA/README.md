# Home Assistant

Home Assistant bleibt die Datenquelle fuer Wall Dashboard, Vacation Mode, Kalender/CalDAV, Household-Kontext, MyWellness Health-Entities, EcoTracker/Energie und Infrastructure/FritzBox-Status.

## RoboterSteve Integration

- Backend liest Home Assistant ueber REST API und konfigurierte Tokens aus `.env`.
- Wall Dashboard nutzt weiterhin `/api/homeassistant/wall`.
- Die Wall-Energie-Seite nutzt `/api/homeassistant/energy`; RoboterSteve spricht EcoTracker nicht direkt an.
- Infrastructure Service liest ausschliesslich Home-Assistant-Entities und speichert eigene Events in `agent-api/data/infrastructure/infrastructure.db`.
- Vacation Mode wird ueber `input_boolean.vacation_mode` gesetzt/gelesen.
- Household prueft offene Tuer-/Fensterkontakte aus Home Assistant und kann bei offenen Kontakten eine Message sowie optional eine mobile Push-Nachricht erzeugen.
- Keine direkte FritzBox API in RoboterSteve.

## Aktuelle Struktur

- `configuration.yaml` bindet die aufgeteilten Home-Assistant-Dateien ein.
- `rest/` enthaelt REST-Sensoren.
- `templates/` enthaelt Template-Sensoren.
- `automations/` enthaelt Automationen.
- `scripts/` enthaelt Scripts.
- `utility_meters.yaml` enthaelt Tageszaehler, z.B. fuer EcoTracker Netzbezug/Einspeisung.

## EcoTracker / Energie

EcoTracker wird in Home Assistant ueber `rest/ecoTracker.yaml`, `templates/ecoTracker.yaml` und `utility_meters.yaml` abgebildet.

Wichtige Entitaeten:

- `sensor.ecotracker_power`
- `sensor.ecotracker_power_avg`
- `sensor.ecotracker_power_phase1`
- `sensor.ecotracker_power_phase2`
- `sensor.ecotracker_power_phase3`
- `sensor.ecotracker_energy_in`
- `sensor.ecotracker_energy_out`
- `sensor.ecotracker_energy_in_today`
- `sensor.ecotracker_energy_out_today`

`energyCounterIn` und `energyCounterOut` werden in Home Assistant nach kWh umgerechnet. Wenn der Zaehler keine Einspeisung liefert, bleibt `sensor.ecotracker_energy_out` verfuegbar und liefert `0`.

## Post-Benachrichtigung

`automations/post.yaml` erzeugt bei erkannter Post eine mobile Benachrichtigung mit dem Tag `briefkasten_post`.

Wenn der Briefkasten geleert wird, sendet Home Assistant `clear_notification` mit demselben Tag. Dadurch wird die vorherige Benachrichtigung auf dem Handy entfernt, statt eine zweite "geleert"-Nachricht zu erzeugen.

`automations/postErkannt.yaml` wird durch `automation: !include_dir_merge_list automations` ebenfalls geladen. Die Datei ist nur sinnvoll, wenn `binary_sensor.briefkasten` noch existiert; sonst sollte sie entfernt oder deaktiviert werden, damit die Postlogik nicht doppelt gepflegt wird.

## Secrets

Keys, Tokens und Integrations-Schluessel gehoeren nicht in README-Dateien. Bitte in `.env`, Home-Assistant-Secrets oder der jeweiligen Integration verwalten.

```text
MEROSS_KEY=<in Home Assistant / Secrets verwalten>
```

## Editionen

Home Assistant bleibt ein Core-Baustein fuer RoboterSteve. Die Personal-App nutzt Home Assistant fuer Wall Dashboard, Energy, Waste, Household, Garden, Infrastructure, MyWellness Health und Vacation.
