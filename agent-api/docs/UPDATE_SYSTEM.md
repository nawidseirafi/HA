# RoboterSteve Update-System V1

Das Update-System nutzt fuer RoboterSteve einen einfachen statischen HTTPS-Server mit `latest.json` und einer ZIP-Datei.

RoboterSteve wird aktuell als lokales Python/systemd-Deployment betrieben. Docker- und ausgelagerte Produkt-Deployments gehoeren nicht in dieses Repository.

## Modus

Empfohlene Zielkonfiguration:

```ini
UPDATE_EXECUTION_MODE=local_systemd
UPDATE_SYSTEMD_SERVICE=agent-api
UPDATE_SYSTEMD_RESTART_DELAY_SECONDS=2
```

Unterstuetzte Modi:

- `dry_run`: Manifest laden, Update simulieren, keine Dateien aendern
- `local`: Legacy-Alias fuer `local_systemd`
- `local_systemd`: ZIP-Datei in ein Python/systemd-Deployment einspielen und danach den systemd-Service zeitverzoegert neu starten
- `local_no_restart`: ZIP-Datei einspielen, ohne automatischen Neustart
- `zip_docker`: Kompatibilitaetsmodus im Update-Service, nicht der RoboterSteve-Standard

V1-Regel:

- RoboterSteve nutzt `local_systemd`.
- `.env`, `config.yaml`, `data/`, `logs/`, `backups/`, `tmp/`, virtuelle Umgebungen und `node_modules/` werden nie ueberschrieben.
- Der Restart wird verzoegert geplant, damit die API dem Frontend noch das Ergebnis melden kann.

## Update-Server

Ein statischer HTTPS-Webserver reicht aus:

```text
https://seirafi.de/robotersteve/
└── robotersteve/
    └── stable/
        ├── latest.json
        └── releases/
            └── robotersteve-0.2.0.zip
```

Konfiguration auf dem Zielrechner:

```ini
UPDATE_BASE_URL=https://seirafi.de/robotersteve/robotersteve
```

Dann wird automatisch gelesen:

```text
https://seirafi.de/robotersteve/robotersteve/stable/latest.json
```

Alternativ kann direkt gesetzt werden:

```ini
UPDATE_MANIFEST_URL=https://seirafi.de/robotersteve/robotersteve/stable/latest.json
```

Prioritaet:

1. `UPDATE_MANIFEST_URL`
2. `UPDATE_BASE_URL + /stable/latest.json`
3. lokales `update-manifest.json`
4. Mock

## Manifest

`latest.json`:

```json
{
  "latest_version": "0.2.0",
  "download_url": "https://seirafi.de/robotersteve/robotersteve/stable/releases/robotersteve-0.2.0.zip",
  "mandatory": false,
  "minimum_version": "0.1.0",
  "sha256": "...",
  "release_notes": [
    "Stabilitaet verbessert",
    "Wall Dashboard beschleunigt"
  ],
  "components": {
    "application": { "update": true },
    "homeassistant": { "update": false },
    "system": { "update": false }
  }
}
```

In V1 wird nur `components.application.update=true` umgesetzt. Home Assistant und System sind im Manifest vorbereitet, werden aber nicht automatisch aktualisiert.

`sha256` ist fuer ZIP-basierte Produktiv-Updates Pflicht. Fehlt die Pruefsumme oder passt sie nicht zur heruntergeladenen ZIP-Datei, bricht die Installation vor dem Entpacken ab. Wenn `size_bytes` gesetzt ist, wird zusaetzlich die Dateigroesse geprueft.

Optional koennen Manifeste signiert werden:

```ini
UPDATE_MANIFEST_PUBLIC_KEY=/opt/roboterSteve/keys/update-public.pem
```

## ZIP-Inhalt

Das Release-ZIP enthaelt ein vollstaendiges deploybares RoboterSteve-Paket:

```text
robotersteve-0.2.0.zip
├── backend/
├── frontend/
├── requirements.txt
├── agent-api.service
├── main.py
├── config.example.yaml
├── .env.example
├── version.json
├── update-manifest.json
└── README_INSTALL.md
```

Nicht enthalten bzw. nie ueberschrieben:

- `.env`
- `config.yaml` mit echten Secrets
- `data/`
- `logs/`
- `backups/`
- `tmp/`
- virtuelle Umgebungen
- `node_modules/`

## Local/systemd Ablauf

Bei `UPDATE_EXECUTION_MODE=local_systemd`:

1. `latest.json` laden
2. Version vergleichen
3. ZIP aus `download_url` herunterladen
4. SHA256 zwingend pruefen und `size_bytes` pruefen, falls gesetzt
5. Backup erstellen
6. ZIP in ein temporaeres Update-Verzeichnis entpacken
7. Struktur validieren: `backend/`, `requirements.txt`, `version.json`
8. erlaubte Dateien aktualisieren
9. Status und Audit-Log schreiben
10. systemd-Restart zeitverzoegert ausloesen
11. Healthcheck pruefen, standardmaessig `http://127.0.0.1:8080/health`

## Backup und Rollback

Backup sichert:

- `config.yaml`
- `.env`
- `data/`
- `settings/`
- `version.json`

Wenn ein Update fehlschlaegt, versucht der Service konservativ:

1. letztes Backup wiederherstellen
2. systemd-Service neu starten
3. Fehler im Audit-Log speichern

Die normale UI zeigt nur eine nutzerfreundliche Meldung. Technische Details stehen nur im Admin-/Dev-Status bereit.

## API

- `GET /api/system/version`
- `GET /api/system/update/check`
- `POST /api/system/update/install`
- `GET /api/system/update/status`
- `GET /api/system/update/admin/status`
- `POST /api/system/update/rollback`

`install` und `rollback` sind nur fuer Administratoren erlaubt.

## Release Build

RoboterSteve-Release bauen:

```bash
cd /Users/nawid/Projects/roboterSteve/agent-api
../venv/bin/python deployment_build.py --version 0.2.0 --base-url https://seirafi.de/robotersteve
```

Erzeugt:

```text
build/robotersteve/                                      # normales installierbares Deployment-Paket
build/updates/robotersteve/stable/latest.json            # Upload auf HTTPS-Update-Server
build/updates/robotersteve/stable/deployment-manifest.json
build/updates/robotersteve/stable/releases/robotersteve-0.2.0.zip
```

Der Builder erzeugt standardmaessig beide Varianten unter `build/`.
`build/robotersteve/` ist das normale lokale Deployment-Paket.
`build/updates/robotersteve/stable/` ist der Upload-Ordner fuer den statischen Update-Server.

Wenn ausnahmsweise nur das lokale Deployment ohne Update-ZIP gebaut werden soll:

```bash
../venv/bin/python deployment_build.py --no-zip
```
