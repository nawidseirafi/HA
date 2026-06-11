# Home Assistant

Home Assistant bleibt die Datenquelle fuer Wall Dashboard, Vacation Mode, Kalender/CalDAV, Household-Kontext, MyWellness Health-Entities und Infrastructure/FritzBox-Status.

## RoboterSteve Integration

- Backend liest Home Assistant ueber REST API und konfigurierte Tokens aus `.env`.
- Wall Dashboard nutzt weiterhin `/api/homeassistant/wall`.
- Infrastructure Service liest ausschliesslich Home-Assistant-Entities und speichert eigene Events in `agent-api/data/infrastructure/infrastructure.db`.
- Vacation Mode wird ueber `input_boolean.vacation_mode` gesetzt/gelesen.
- Keine direkte FritzBox API in RoboterSteve.

## Secrets

Keys, Tokens und Integrations-Schluessel gehoeren nicht in README-Dateien. Bitte in `.env`, Home-Assistant-Secrets oder der jeweiligen Integration verwalten.

```text
MEROSS_KEY=<in Home Assistant / Secrets verwalten>
```

## Editionen

Home Assistant bleibt ein Core-Baustein und kann je nach aktiver RoboterSteve Edition eingebunden werden. `personal` nutzt Home Assistant fuer Wall Dashboard, Waste, Household, Infrastructure, MyWellness Health und Vacation. `seniorcare` nutzt Home Assistant als spaetere Sensorik- und Statusquelle, ohne private Agenten wie Finance & Contracts, Market, MyWellness oder Vacation vorauszusetzen.
