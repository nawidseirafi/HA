# RoboterSteve Update-System V1

Das Update-System ist edition-unabhaengig. V1 nutzt fuer Releases einen einfachen statischen HTTPS-Server mit `latest.json` und einer ZIP-Datei.

Keine Docker Registry ist notwendig.

## Edition-Modi

Personal bleibt ein normales Deployment ohne Docker:

```ini
ROBOTERSTEVE_EDITION=personal
UPDATE_EXECUTION_MODE=local
```

SeniorCare ist eine Docker-Edition, wird aber per ZIP aktualisiert:

```ini
ROBOTERSTEVE_EDITION=seniorcare
UPDATE_EXECUTION_MODE=zip_docker
UPDATE_DEPLOYMENT_DIR=/opt/seniorcare
UPDATE_COMPOSE_PROJECT_DIR=/opt/seniorcare
UPDATE_COMPOSE_FILE=docker-compose.yml
```

Unterstuetzte Modi:

- `dry_run`: Manifest laden, Update simulieren, keine Dateien aendern
- `local`: ZIP-Datei in ein normales Python/systemd-Deployment einspielen, fuer Personal
- `zip_docker`: ZIP-Datei in eine Docker-Edition einspielen und lokal per Compose neu bauen, fuer SeniorCare

Der alte Docker-Image/Registry-Modus wird in V1 nicht verwendet.

## Update-Server

Ein statischer HTTPS-Webserver reicht aus:

```text
https://seirafi.de/robotersteve/
└── seniorcare/
    └── stable/
        ├── latest.json
        └── releases/
            └── seniorcare-0.2.0.zip
```

Konfiguration auf dem Zielrechner:

```ini
UPDATE_BASE_URL=https://seirafi.de/robotersteve
```

Dann wird automatisch gelesen:

```text
https://seirafi.de/robotersteve/<edition>/stable/latest.json
```

Alternativ kann direkt gesetzt werden:

```ini
UPDATE_MANIFEST_URL=https://seirafi.de/robotersteve/seniorcare/stable/latest.json
```

Prioritaet:

1. `UPDATE_MANIFEST_URL`
2. `UPDATE_BASE_URL + /<edition>/stable/latest.json`
3. lokales `update-manifest.json`
4. Mock

## Manifest

`latest.json`:

```json
{
  "latest_version": "0.2.0",
  "download_url": "https://seirafi.de/robotersteve/seniorcare/stable/releases/seniorcare-0.2.0.zip",
  "mandatory": false,
  "minimum_version": "0.1.0",
  "sha256": "...",
  "release_notes": [
    "Stabilitaet verbessert",
    "Einrichtung verbessert"
  ],
  "components": {
    "application": { "update": true },
    "homeassistant": { "update": false },
    "ollama": { "update": false },
    "system": { "update": false }
  }
}
```

In V1 wird nur `components.application.update=true` umgesetzt. Home Assistant, Ollama und System sind im Manifest vorbereitet, werden aber nicht automatisch aktualisiert.

`sha256` wird geprueft, wenn gesetzt. Wenn `sha256` leer ist, wird das Update fuer V1/Dev erlaubt, aber das ist fuer produktive Releases nicht empfohlen.

Optional koennen Manifeste signiert werden:

```ini
UPDATE_MANIFEST_PUBLIC_KEY=/opt/seniorcare/keys/update-public.pem
```

Der Builder kann signieren:

```bash
UPDATE_MANIFEST_SIGNING_KEY=/secure/update-private.pem ../venv/bin/python tools/build_edition.py seniorcare --version 0.2.0 --base-url https://seirafi.de/robotersteve
```

## ZIP-Inhalt

Das Release-ZIP enthaelt ein vollstaendiges deploybares Edition-Paket:

```text
seniorcare-0.2.0.zip
├── backend/
├── frontend/
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── config.example.yaml
├── version.json
├── update-manifest.json
└── README.md oder README_INSTALL.md
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

## ZIP-Docker Ablauf

Bei `UPDATE_EXECUTION_MODE=zip_docker`:

1. `latest.json` laden
2. Version vergleichen
3. ZIP aus `download_url` herunterladen
4. SHA256 pruefen, falls gesetzt
5. Backup erstellen unter `/opt/<edition>/backups/`, z. B. `/opt/seniorcare/backups/`
6. ZIP nach `/opt/<edition>/tmp/update-<version>/` entpacken
7. Struktur validieren: `backend/`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `version.json`
8. `docker compose down`
9. erlaubte Dateien aktualisieren
10. `docker compose up -d --build`
11. Healthcheck pruefen, standardmaessig `http://127.0.0.1:8080/health`
12. Status und Audit-Log schreiben

Die RoboterSteve/SeniorCare-Anwendung wird lokal aus dem ZIP gebaut. Es gibt kein `docker compose pull` fuer `robotersteve-api` und keine externe Docker Registry.

`docker-compose.yml` fuer SeniorCare baut lokal:

```yaml
services:
  robotersteve-api:
    build: .
    ports:
      - "8080:8080"
```

Externe Standard-Images wie `ollama/ollama` duerfen weiterhin verwendet werden. Sie werden in V1 aber nicht automatisch aktualisiert.

## Backup und Rollback

Backup sichert im ZIP-Docker-Modus:

- `config.yaml`
- `.env`
- `data/`
- `settings/`
- `editions/`
- `version.json`
- `docker-compose.yml`

Wenn ein ZIP-Docker-Update fehlschlaegt, versucht der Service konservativ:

1. letztes Backup wiederherstellen
2. `docker compose up -d --build` erneut ausfuehren
3. Fehler im Audit-Log speichern

Die Kunden-UI zeigt nur:

```text
Update fehlgeschlagen. Das vorherige System wurde wiederhergestellt.
```

Technische Details stehen nur im Admin-/Dev-Modus bereit.

## API

- `GET /api/system/version`
- `GET /api/system/update/check`
- `POST /api/system/update/install`
- `GET /api/system/update/status`
- `GET /api/system/update/admin/status`
- `POST /api/system/update/rollback`

`install` und `rollback` sind nur fuer den Administrator erlaubt.

Die normale Kunden-UI zeigt keine technischen Details wie Docker, ZIP, Compose, Ollama, Home Assistant, System, Channel, Registry oder Image.

## Release Build

SeniorCare ZIP-Release bauen:

```bash
cd /Users/nawid/Projects/roboterSteve/agent-api
../venv/bin/python tools/build_edition.py seniorcare --version 0.2.0 --base-url https://seirafi.de/robotersteve
```

Erzeugt:

```text
build/seniorcare/                              # normales installierbares Deployment-Paket
build/updates/seniorcare/stable/latest.json             # Upload auf HTTPS-Update-Server
build/updates/seniorcare/stable/deployment-manifest.json # Upload auf HTTPS-Update-Server
build/updates/seniorcare/stable/releases/seniorcare-0.2.0.zip
```

Der Edition Builder erzeugt standardmaessig beide Varianten unter `build/`.
`build/<edition>/` ist das normale lokale Deployment-Paket.
`build/updates/<edition>/stable/` ist der Upload-Ordner fuer den statischen Update-Server.
`--zip` wird aus Kompatibilitaet weiter akzeptiert, ist aber nicht mehr notwendig.

Diese Struktur kann direkt auf den HTTPS-Server hochgeladen werden:

```text
robotersteve/
└── seniorcare/
    └── stable/
        ├── latest.json
        └── releases/
            └── seniorcare-0.2.0.zip
```

Personal bleibt moeglich:

```bash
../venv/bin/python tools/build_edition.py personal --version 0.2.0 --base-url https://seirafi.de/robotersteve
```

Personal nutzt weiterhin `UPDATE_EXECUTION_MODE=local` und kein Docker.
Wenn ausnahmsweise nur das lokale Deployment ohne Update-Paket gebaut werden soll:

```bash
../venv/bin/python tools/build_edition.py personal --no-update
```
