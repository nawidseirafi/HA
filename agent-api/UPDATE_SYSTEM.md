# RoboterSteve Update-System

Das Update-System ist edition-unabhaengig und steht fuer Personal, SeniorCare und zukuenftige Editionen ueber den Core-Service `system` bereit.

## Ebenen

- Application Update: RoboterSteve / SeniorCare Anwendung
- AI Runtime Update: Ollama und Modelle
- Home Assistant Update: Home Assistant Container
- System Update: Debian, Docker und Container Runtime

## API

- `GET /api/system/version`
- `GET /api/system/update/check?channel=stable`
- `POST /api/system/update/install`
- `GET /api/system/update/status`
- `GET /api/system/update/admin/status`
- `POST /api/system/update/rollback`

`install` und `rollback` sind nur fuer den angemeldeten Administrator erlaubt.

`/api/system/update/status` ist bewusst kundenfreundlich und enthaelt keine technischen Details:

```json
{
  "product": "SeniorCare",
  "current_version": "0.1.0",
  "latest_version": "0.2.0",
  "update_available": true,
  "last_checked": "...",
  "status": "idle",
  "release_notes": ["Verbesserte Stabilitaet"]
}
```

Technische Details stehen nur im Dev-/Admin-Endpunkt `/api/system/update/admin/status` bereit.

## Version

Versionen werden aus folgender Reihenfolge gelesen:

1. Environment / `.env`
2. `version.json`
3. `config.yaml -> version`
4. Fallback `0.1.0`

Wichtige Variablen:

```ini
ROBOTERSTEVE_VERSION=1.2.0
ROBOTERSTEVE_BUILD=2026.06.08
ROBOTERSTEVE_COMMIT=abcdef
UPDATE_SERVER_URL=https://updates.robotersteve.ai
UPDATE_MANIFEST_URL=https://updates.robotersteve.ai/seniorcare/stable/latest.json
UPDATE_MANIFEST_PATH=update-manifest.json
UPDATE_CHANNEL=stable
UPDATE_EXECUTION_MODE=dry_run
UPDATE_COMPOSE_PROJECT_DIR=.
UPDATE_COMPOSE_FILE=docker-compose.yml
UPDATE_HEALTHCHECK_URL=http://127.0.0.1:8080/health
UPDATE_MANIFEST_PUBLIC_KEY=
```

## Update-Server

V1 unterstuetzt einen statischen HTTPS-Update-Server. Dafuer reicht:

```text
https://updates.robotersteve.ai/
└── seniorcare/
    └── stable/
        ├── latest.json
        └── releases/
            └── seniorcare-0.2.0.zip
```

Empfohlen ist:

```ini
UPDATE_MANIFEST_URL=https://updates.robotersteve.ai/seniorcare/stable/latest.json
UPDATE_EXECUTION_MODE=local
```

`latest.json`:

```json
{
  "schema_version": 1,
  "product": "seniorcare",
  "latest_version": "0.2.0",
  "download_url": "https://updates.robotersteve.ai/seniorcare/stable/releases/seniorcare-0.2.0.zip",
  "sha256": "...",
  "size_bytes": 12345678,
  "mandatory": false,
  "minimum_version": "0.1.0",
  "release_notes": [
    "Stabilitaet verbessert",
    "Benachrichtigungen optimiert"
  ],
  "components": {
    "application": { "update": true },
    "homeassistant": { "update": false },
    "ollama": { "update": false },
    "system": { "update": false }
  }
}
```

`sha256` ist fuer ZIP-Installation Pflicht. ZIP-Dateien ohne passende Pruefsumme werden nicht installiert.

Optional kann das Manifest signiert werden. Dann wird im Zielsystem gesetzt:

```ini
UPDATE_MANIFEST_PUBLIC_KEY=/opt/roboterSteve/keys/update-public.pem
```

Das Manifest muss dann ein Feld `signature` enthalten. Die Signatur ist base64-kodiert und wird ueber die kanonische JSON-Struktur ohne `signature` mit `openssl dgst -sha256 -verify` geprueft. Der Edition-Builder kann Manifeste signieren:

```bash
UPDATE_MANIFEST_SIGNING_KEY=/secure/update-private.pem python tools/build_edition.py seniorcare
```

## Release Build

Der Edition-Builder erzeugt neben `build/<edition>/` automatisch Release-Artefakte:

```text
build/
├── personal/
│   └── deployment-manifest.json
└── releases/
    └── personal/
        ├── personal-0.1.0.zip
        ├── latest.json
        └── deployment-manifest.json
```

Aufruf:

```bash
python tools/build_edition.py personal
python tools/build_edition.py seniorcare
```

`latest.json` ist direkt fuer den statischen Update-Server nutzbar. Die `download_url` wird standardmaessig als Beispiel-URL erzeugt. Fuer echte Releases kann der Basis-Pfad gesetzt werden:

```bash
UPDATE_RELEASE_BASE_URL=https://updates.example.com/seniorcare/stable/releases python tools/build_edition.py seniorcare
```

Das ZIP enthaelt ein `deployment-manifest.json`. Die externe `build/releases/<edition>/deployment-manifest.json` enthaelt zusaetzlich SHA256 und Groesse des ZIPs.

Alternativ bleibt der dynamische Kompatibilitaets-Endpunkt moeglich. Wenn `UPDATE_SERVER_URL` gesetzt ist und nicht auf `.json` endet, fragt der Service:

```text
GET <UPDATE_SERVER_URL>/latest?edition=<edition>&channel=stable&version=<version>
```

## Lokales Update-Manifest

Ohne `UPDATE_MANIFEST_URL` und ohne `UPDATE_SERVER_URL` wird zuerst `update-manifest.json` gelesen. Dadurch kann spaeter ein echter Update-Server angeschlossen werden, ohne die Engine umzubauen. Der Server muss dieselbe `latest`-Struktur liefern.

Aufloesungsreihenfolge:

1. `UPDATE_MANIFEST_URL` oder `updates.manifest_url`
2. `UPDATE_SERVER_URL` oder `updates.server_url`
3. `UPDATE_MANIFEST_PATH` oder `updates.manifest_path`
4. lokaler Mock aus `updates.mock_latest`

Minimalstruktur:

```json
{
  "schema_version": 1,
  "editions": {
    "seniorcare": {
      "channels": {
        "stable": {
          "latest_version": "0.2.0",
          "download_url": "...",
          "sha256": "...",
          "size_bytes": 12345678,
          "mandatory": false,
          "minimum_version": "0.1.0",
          "components": {
            "application": { "update": true },
            "homeassistant": { "update": false },
            "ollama": { "update": false },
            "system": { "update": false }
          },
          "release_notes": ["..."],
          "artifacts": {}
        }
      }
    }
  }
}
```

Die Komponenten steuern nur intern, was aktualisiert wird. In der normalen UI werden diese technischen Details nicht angezeigt. Ohne Server und ohne Manifest wird der lokale Mock verwendet. Das System bleibt offline funktionsfaehig.

## Kunden-UI

Die normale Update-Seite zeigt nur:

- Produktname
- aktuelle Version
- Update-Status
- letzte Pruefung
- Release Notes
- `Nach Updates suchen`
- `Update installieren`

Nicht sichtbar sind Kanal, Docker, Debian, Ollama, Home Assistant, Commit, `dry_run`, Rollback und interne Komponenten. Technische Details werden nur angezeigt, wenn `ROBOTERSTEVE_DEV_MODE=true` gesetzt ist oder ein Entwickler-Admin den Admin-Endpunkt nutzt.

## Docker-Modus

Standard ist sicherer Dry-Run:

```ini
UPDATE_EXECUTION_MODE=dry_run
```

Produktive ZIP-Deployments aktivieren:

```ini
UPDATE_EXECUTION_MODE=local
```

Dann wird das Application-ZIP geladen, per SHA256 geprueft und in das Deployment-Verzeichnis eingespielt. Dieser Modus ist fuer normale Personal-/Python-Deployments vorgesehen. Rollback ueber die UI ist in diesem Modus bewusst deaktiviert, weil Dateikopie-Rollbacks ohne Datenbankmigrationen und Service-Orchestrierung fuer Kundenbetrieb riskant sind.

Nie ueberschrieben werden:

- `.env`
- `data/`
- `logs/`
- Datenbanken wie `*.db`, `*.sqlite`
- `node_modules/`
- virtuelle Umgebungen

Produktive Docker-Deployments aktivieren:

```ini
UPDATE_EXECUTION_MODE=docker
UPDATE_COMPOSE_PROJECT_DIR=/opt/roboterSteve
UPDATE_COMPOSE_FILE=docker-compose.yml
UPDATE_HEALTHCHECK_URL=http://127.0.0.1:8080/health
```

Dann startet das Update im Hintergrund:

```bash
docker compose pull
docker compose down
docker compose up -d
```

Der Hintergrundmodus ist notwendig, weil `docker compose down` die laufende API beendet.

Docker-Modus ist der Produktmodus fuer SeniorCare. Vor Installation und Rollback wird geprueft:

- `docker` ist verfuegbar
- `docker compose` oder `docker-compose` ist verfuegbar
- `UPDATE_COMPOSE_FILE` existiert

Application-ZIP-Dateien werden im Docker-Modus nicht in das laufende Deployment kopiert. Das Manifest steuert nur, welche Komponenten aktualisiert werden. Die eigentliche Aktualisierung erfolgt ueber Compose/Image-Pull.

Wichtig fuer vermarktete SeniorCare-Installationen: Der API-Service muss in `docker-compose.yml` ein echtes Produkt-Image verwenden, z. B.

```yaml
services:
  robotersteve-api:
    image: robotersteve/seniorcare-api:latest
```

Ein Compose-Setup, das nur `python:3.12-slim` startet und den lokalen Quellcode per Volume einbindet, ist nicht updatefaehig ueber `docker compose pull`. Der Edition-Builder erzeugt fuer Docker-Editionen deshalb ein `Dockerfile` und eine Compose-Datei mit `ROBOTERSTEVE_API_IMAGE`.

Weitere Ebenen:

```bash
docker compose pull ollama
docker compose up -d ollama
docker exec ollama ollama pull <model>
docker compose pull homeassistant
docker compose up -d homeassistant
apt update
apt upgrade -y
apt autoremove -y
```

Ein Debian-Reboot wird nur als Hinweis gemeldet. Das System rebootet nicht automatisch.

## Backup

Vor Installation wird ein `tar.gz`-Backup erstellt unter:

```text
/opt/roboterSteve/backups/
```

Gesichert werden:

- `config.yaml`
- `.env`
- `data/`
- `editions/`
- `settings/`
- Agent-Konfigurationen

## Rollback

Rollback ist nur fuer Docker-basierte Deployments aktiviert:

```ini
UPDATE_EXECUTION_MODE=docker
```

Ablauf:

1. `docker compose down`
2. letztes Backup wiederherstellen
3. `docker compose up -d`
4. Version/Status/Audit-Log aktualisieren

Bei `UPDATE_EXECUTION_MODE=local` oder `dry_run` lehnt die API Rollback ab. Das ist Absicht. Lokale Dateikopie-Deployments sollten fuer Produktkunden nicht per Ein-Klick-Rollback zurueckgesetzt werden, solange Datenbankmigrationen nicht transaktional versioniert sind.

## Empfohlene Produktaufteilung

Personal, normales Deployment:

```ini
ROBOTERSTEVE_EDITION=personal
UPDATE_EXECUTION_MODE=local
UPDATE_MANIFEST_URL=https://updates.example.com/personal/stable/latest.json
```

SeniorCare, Docker-Deployment:

```ini
ROBOTERSTEVE_EDITION=seniorcare
UPDATE_EXECUTION_MODE=docker
UPDATE_MANIFEST_URL=https://updates.example.com/seniorcare/stable/latest.json
UPDATE_COMPOSE_PROJECT_DIR=/opt/roboterSteve
UPDATE_COMPOSE_FILE=docker-compose.yml
UPDATE_HEALTHCHECK_URL=http://127.0.0.1:8080/health
```

Fuer vermarktete SeniorCare-Installationen sollte `UPDATE_MANIFEST_PUBLIC_KEY` gesetzt werden, damit nur signierte Update-Manifeste akzeptiert werden.

Gesichert werden:

- `config.yaml`
- `.env`
- `editions/`
- `data/`
- `settings/`
- `backend/agents/`

Falls `/opt/roboterSteve/backups` im Entwicklungsmodus nicht beschreibbar ist, faellt der Service auf `data/backups/updates/` zurueck. Backups werden mit Dateimodus `0600` angelegt, soweit vom Dateisystem unterstuetzt.

## Audit Log

Installationen, Rollbacks und Fehler werden protokolliert:

```text
logs/update_audit.jsonl
```

Jeder Eintrag enthaelt Zeitpunkt, Benutzer, Aktion, alte Version, neue Version und technische Details.

## Scheduler

Der Scheduler legt automatisch einen Plattform-Task an, wenn `system` in der Edition aktiviert ist:

```text
System Updatepruefung, Cron 0 7 * * *
```

Wenn ein Update verfuegbar ist, erzeugt der Update-Service eine Message mit `source=system` und `category=updates`.
