# Garden Agent

Der Garden Agent ist der Fachagent fuer Gartenautomatisierung in der Personal Edition.

## Aktueller Stand

Der Agent arbeitet aktuell beratend. Er liest Home-Assistant-Entitaeten, erstellt einen Garden-Snapshot, speichert diesen in `data/garden/garden.db` und erzeugt einfache regelbasierte Empfehlungen.

Automatische Steuerung ist noch nicht aktiv. Bewaesserung, Mähroboter oder andere Smart-Home-Geraete werden vom Agenten nicht geschaltet.

## Erkannte Entitaeten

- `lawn_mower.*` fuer Mähroboter
- Bodenfeuchte-Sensoren ueber typische Namen, Friendly Names und Device Classes
- Bewaesserung ueber `switch`, `valve` oder `input_boolean` mit Garten-/Bewaesserungsbezug
- `weather.*` fuer Wetterkontext

## Architektur

- `manifest.yaml`: Agent-Metadaten, Route, Runtime-Service und Scheduler-Default
- `config.yaml`: Aktivierung, Schwellwerte, Entity-Erkennung und Datenbankpfad
- `service.py`: Home-Assistant-Erkennung, Bewertung, Control-Actions
- `store.py`: SQLite-Persistenz fuer Snapshots
- `routes.py`: HTTP API unter `/api/garden`

## Scheduler

Der Manifest-Default plant eine taegliche Statuspruefung um 07:00 Uhr.

## KI

Die Agent Map zeigt bereits eine OpenAI-Verbindung, damit die spaetere KI-Auswertung architektonisch vorgesehen ist. Aktuell ruft der Garden Agent aber noch kein LLM auf.

Geplante KI-Aufgaben:

- Bewaesserungsbedarf aus Bodenfeuchte, Wetter und Verlauf einschaetzen
- Mähroboter-Zeitfenster mit Boden-/Wetterlage abgleichen
- Auffaellige Gartenmuster erkennen
- Empfehlungen und Tagesplaene erzeugen

KI- oder Agentenlogik darf Geraete erst steuern, wenn dafuer regelbasierte Freigaben und Sicherheitslogik umgesetzt sind.
