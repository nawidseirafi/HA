# RoboterSteve Agent API Deployment

Diese Anleitung beschreibt das RoboterSteve-Deployment auf einem Debian-Zielrechner. Ziel ist:

- FastAPI laeuft als systemd-Service auf Port `8080`
- Die gebaute React-GUI wird direkt von FastAPI ausgeliefert
- Zugriff im Browser ueber `http://robotersteve.local:8080`
- `agent-api` ist die deploybare Anwendungseinheit

## Zielstruktur

```text
/opt/roboterSteve/
├── agent-api/
│   ├── backend/
│   ├── frontend/
│   ├── config.yaml
│   └── requirements.txt
└── venv/
```

Wichtig: Die alte `ai-agent/`-Struktur wird nicht mehr fuer Deployments verwendet. Agenten, Services und Datenpfade liegen unter `agent-api/`.

## Debian vorbereiten

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nodejs npm avahi-daemon rsync
sudo hostnamectl set-hostname robotersteve
sudo systemctl enable --now avahi-daemon
```

Danach ist der Rechner im lokalen Netzwerk erreichbar unter:

```text
http://robotersteve.local:8080
```

Falls eine Firewall aktiv ist:

```bash
sudo ufw allow 8080/tcp
sudo ufw allow 5353/udp
```

## Empfohlener Deployment-Weg: RoboterSteve Build

Der aktuelle Standard ist `deployment_build.py`. Dadurch wird ein deploybares RoboterSteve-Paket plus Update-Artefakte erzeugt. Private Daten, Logs, `.env`, Datenbanken, `node_modules`, `venv` und `__pycache__` werden nicht kopiert.

Der Builder erzeugt beide Varianten unter `build/`:
das normale Deployment-Paket unter `build/robotersteve/` und die Update-Server-Dateien unter `build/updates/robotersteve/stable/`.

Auf dem Entwicklungsrechner:

```bash
cd /Users/nawid/Projects/roboterSteve/agent-api
../venv/bin/python deployment_build.py
```

Ergebnis:

```text
agent-api/build/robotersteve/
├── backend/
├── frontend/dist/
├── config.example.yaml
├── .env.example
├── requirements.txt
└── README_INSTALL.md
```

RoboterSteve ist ein normales Python/systemd-Deployment. Es wird bewusst keine `docker-compose.yml` erzeugt.

Auf den Zielrechner kopieren:

```bash
rsync -av --delete \
  --exclude 'data' \
  --exclude 'logs' \
  --exclude '.env' \
  --exclude 'config.yaml' \
  /Users/nawid/Projects/roboterSteve/agent-api/build/robotersteve/ \
  user@robotersteve.local:/opt/roboterSteve/agent-api/
```

Wenn du bestehende lokale Datenbanken auf dem Zielrechner behalten willst, schuetzt der empfohlene `rsync`-Befehl `data/`, `logs/`, `.env` und `config.yaml` explizit vor Loeschung. Der Build selbst enthaelt diese privaten Dateien nicht.

Beim ersten Deployment auf einem leeren Zielsystem erzeugst du die echte Konfiguration aus den Beispieldateien:

```bash
ssh user@robotersteve.local
cd /opt/roboterSteve/agent-api
cp config.example.yaml config.yaml
cp .env.example .env
nano config.yaml
nano .env
```

Danach sollte `config.yaml` und `.env` nicht mehr per Build ueberschrieben werden.


Optionale persistente Daten liegen unter `agent-api/data/`. Der Build enthaelt dieses Verzeichnis bewusst nicht. Wenn du bestehende Datenbanken oder Invoice-Archive migrieren willst, kopiere sie separat nach `/opt/roboterSteve/agent-api/data/`.


## Legacy-Deployment: komplettes Entwicklungsverzeichnis synchronisieren

Nur nutzen, wenn du bewusst das komplette Entwicklungsprojekt auf den Zielrechner legen willst. Dann musst du selbst aufpassen, dass keine privaten oder lokalen Artefakte mitkopiert werden.

```bash
rsync -av --delete \
  --exclude 'build' \
  --exclude 'data' \
  --exclude 'logs' \
  --exclude '.env' \
  --exclude '*.db' \
  --exclude 'frontend/node_modules' \
  --exclude 'frontend/dist' \
  --exclude '__pycache__' \
  agent-api/ user@robotersteve.local:/opt/roboterSteve/agent-api/
```

## Python-Umgebung installieren

Auf dem Zielrechner:

```bash
cd /opt/roboterSteve
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r agent-api/requirements.txt
```


## Frontend manuell bauen

Normalerweise erledigt `deployment_build.py` den Frontend-Build automatisch. Dieser Abschnitt ist nur fuer manuelle Legacy-Deployments relevant.

Wenn FastAPI `frontend/dist` ausliefert, ist immer der zuletzt gebaute Frontend-Stand aktiv.

Moeglich sind zwei Varianten.

### Variante A: Frontend auf dem Zielrechner bauen

```bash
cd /opt/roboterSteve/agent-api/frontend
npm install
npm run build
```

Wenn `agent-api/frontend/dist` existiert, liefert FastAPI die GUI direkt unter Port `8080` aus.

### Variante B: Frontend auf dem Entwicklungsrechner bauen

Auf dem Entwicklungsrechner:

```bash
cd agent-api/frontend
npm install
npm run build
```

Danach muss `dist/` mit auf den Zielrechner kopiert werden. Wichtig: Bei dieser Variante `frontend/dist` nicht vom Sync ausschliessen:

```bash
rsync -av --delete \
  --exclude 'frontend/node_modules' \
  --exclude '__pycache__' \
  agent-api/ user@ziel:/opt/roboterSteve/agent-api/
```

Alternativ nur den gebauten Frontend-Ordner aktualisieren:

```bash
rsync -av --delete agent-api/frontend/dist/ user@ziel:/opt/roboterSteve/agent-api/frontend/dist/
```

Danach den Service neu starten, damit FastAPI die aktuellen statischen Dateien ausliefert:

```bash
sudo systemctl restart agent-api
```

## Umgebungsvariablen

Secrets sollten nicht direkt ins Git-Repo. Lege auf dem Zielrechner eine Environment-Datei an:

```bash
sudo nano /etc/robotersteve-agent-api.env
```

Beispiel:

```ini
AGENT_API_USERNAME=admin
AGENT_API_PASSWORD=change-me
AGENT_API_JWT_SECRET=change-me-long-random-secret

HA_URL=http://homeassistant.local:8123
HA_TOKEN=change-me

MY_WELLNESS_TOKEN=change-me
MY_WELLNESS_USER_ID=change-me
MY_WELLNESS_FACILITY_ID=change-me

INVOICE_EMAIL_HOST=imap.example.com
INVOICE_EMAIL_USERNAME=user@example.com
INVOICE_EMAIL_PASSWORD=change-me

OPENAI_API_KEY=change-me
GEMINI_API_KEY=change-me
CLAUDE_API_KEY=change-me
```

Rechte setzen:

```bash
sudo chmod 600 /etc/robotersteve-agent-api.env
```

Hinweis: Environment-Variablennamen mit Bindestrich sind ungueltig. Verwende `HA_TOKEN`, nicht `HA-TOKEN`.



## Build Kurzreferenz

Der bevorzugte Weg fuer produktionsnahe Artefakte ist der RoboterSteve Builder:

```bash
cd agent-api
../venv/bin/python deployment_build.py
```

Erzeugt wird:

```text
agent-api/build/robotersteve/
├── backend/
├── frontend/dist/
├── config.example.yaml
├── .env.example
├── requirements.txt
└── README_INSTALL.md
```

Hinweis: RoboterSteve ist ein systemd-Deployment und enthaelt keine `docker-compose.yml`.

Diese Build-Verzeichnisse enthalten keine privaten Datenbanken, Logs, `.env`, `node_modules`, `venv` oder `__pycache__`.

Update-Server-Artefakte werden parallel erzeugt:

```bash
../venv/bin/python deployment_build.py --version 0.2.0 --base-url https://seirafi.de/robotersteve
```

Dann gilt:

```text
agent-api/build/robotersteve/                              # normales Deployment-Paket
agent-api/build/updates/robotersteve/stable/latest.json    # Upload auf HTTPS-Server
agent-api/build/updates/robotersteve/stable/releases/*.zip # Upload auf HTTPS-Server
```

Deployment eines Builds:

```bash
rsync -av --delete --exclude 'data' --exclude 'logs' --exclude '.env' --exclude 'config.yaml' agent-api/build/robotersteve/ user@robotersteve.local:/opt/roboterSteve/agent-api/
```

Auf dem Zielsystem muss die Environment-Datei zum systemd-Deployment passen:

```ini
UPDATE_EXECUTION_MODE=local_systemd
UPDATE_SYSTEMD_SERVICE=agent-api
UPDATE_SYSTEMD_RESTART_DELAY_SECONDS=2
```

Fuer Updates ueber die UI muss der systemd-Restart moeglich sein.
Wenn die Anwendung als `root` laeuft, ist keine sudoers-Regel notwendig.
Wenn sie als eigener Service-User laeuft, ist eine eng begrenzte sudoers-Regel fuer diesen User notwendig:

```bash
sudo visudo -f /etc/sudoers.d/robotersteve-update
```

```text
robotersteve ALL=NOPASSWD: /usr/bin/systemd-run --on-active=2 systemctl restart agent-api, /bin/systemctl restart agent-api, /usr/bin/systemctl restart agent-api
```

Der Update-Service plant den Restart verzoegert, damit die API dem Frontend noch den Erfolg melden kann.

## systemd-Service

Datei erstellen:

```bash
sudo nano /etc/systemd/system/agent-api.service
```

Inhalt:

```ini
[Unit]
Description=RoboterSteve Agent API
After=network.target

[Service]
WorkingDirectory=/opt/roboterSteve/agent-api
EnvironmentFile=/etc/robotersteve-agent-api.env
ExecStart=/opt/roboterSteve/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8080 --log-level info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Service aktivieren:

```bash
sudo systemctl daemon-reload
sudo systemctl enable agent-api
sudo systemctl start agent-api
```

Pruefen:

```bash
sudo systemctl status agent-api
journalctl -u agent-api -f
```

## Betrieb

Start:

```bash
sudo systemctl start agent-api
```

Stop:

```bash
sudo systemctl stop agent-api
```

Restart nach Code- oder Config-Aenderung:

```bash
sudo systemctl restart agent-api
```

Nach Aenderung an `/etc/systemd/system/agent-api.service`:

```bash
sudo systemctl daemon-reload
sudo systemctl restart agent-api
```

Autostart deaktivieren:

```bash
sudo systemctl disable agent-api
```

## Zugriff

GUI:

```text
http://robotersteve.local:8080
```

Swagger/API:

```text
http://robotersteve.local:8080/docs
```

Healthcheck:

```bash
curl http://robotersteve.local:8080/health
```

## Update-Deployment

Empfohlen: RoboterSteve neu bauen, kopieren, Requirements installieren, Service neu starten.

Auf dem Entwicklungsrechner:

```bash
cd /Users/nawid/Projects/roboterSteve/agent-api
../venv/bin/python deployment_build.py
rsync -av --delete --exclude 'data' --exclude 'logs' --exclude '.env' --exclude 'config.yaml' build/robotersteve/ user@robotersteve.local:/opt/roboterSteve/agent-api/
```

Auf dem Zielrechner:

```bash
cd /opt/roboterSteve
./venv/bin/pip install -r agent-api/requirements.txt
sudo systemctl restart agent-api
```

## Typische Fehler

### `ModuleNotFoundError: No module named 'requests'`

`agent-api/requirements.txt` wurde nicht installiert oder die systemd-Unit nutzt die falsche Python-Umgebung:

```bash
cd /opt/roboterSteve
./venv/bin/pip install -r agent-api/requirements.txt
sudo systemctl restart agent-api
```

### `{"detail":"Document file not found"}`

Die Invoice-Datenbank zeigt auf Dateien, die auf dem Zielrechner fehlen oder frueher absolute Pfade vom Entwicklungsrechner hatten.

Pruefen:

```bash
ls -la /opt/roboterSteve/agent-api/data/invoices/archive
ls -la /opt/roboterSteve/agent-api/data/invoices/invoices.db
```

Daten erneut kopieren:

```bash
rsync -av agent-api/data/invoices/ user@ziel:/opt/roboterSteve/agent-api/data/invoices/
sudo systemctl restart agent-api
```

### Refresh auf Unterseiten liefert `{"detail":"Not Found"}`

Der Backend-Code muss den SPA-Fallback fuer React enthalten. Danach neu deployen und Service restarten.

### `robotersteve.local` wird nicht gefunden

Auf dem Zielrechner:

```bash
hostname
systemctl status avahi-daemon
sudo systemctl restart avahi-daemon
```

Vom Client:

```bash
ping robotersteve.local
```

Falls es weiter nicht geht, pruefe Router, VLAN/Gastnetz und Firewall.
