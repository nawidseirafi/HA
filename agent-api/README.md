# Local Agent API

Zentrale FastAPI-Schnittstelle, um lokale Agenten vom Mini-PC aus über Home Assistant, iPhone Shortcuts oder andere Tools zu starten.

## Setup

Lokale Entwicklung in diesem Projekt nutzt das gemeinsame `venv` auf Repo-Ebene:

```bash
source venv/bin/activate
pip install -r agent-api/requirements.txt
```

Auf dem Mini-PC kann spaeter eine eigene venv ausserhalb dieses Verzeichnisses verwendet werden.

## Start

```bash
cd agent-api
uvicorn main:app --host 0.0.0.0 --port 8080
```

Danach ist die API im lokalen Netzwerk unter `http://<mini-pc-ip>:8080` erreichbar.

## Endpoints

```text
GET  /health
GET  /agents
GET  /agents/status
POST /agents/invoices/run
POST /agents/invoices/upload
POST /agents/vacation/run
```

## Beispiele

```bash
curl http://localhost:8080/health
curl http://localhost:8080/agents
curl http://localhost:8080/agents/status
curl -X POST http://localhost:8080/agents/invoices/run
curl -X POST http://localhost:8080/agents/vacation/run
curl -F "file=@rechnung.pdf" http://localhost:8080/agents/invoices/upload
```

Uploads fuer Rechnungen werden unter `storage/uploads/invoices` gespeichert. Der Agent-Status inklusive `last_run` wird in `storage/status.json` persistiert. Die aktuelle Implementierung triggert und loggt nur; echte Rechnungsverarbeitung und Vacation-Logik koennen spaeter in den Agent-Klassen angebunden werden.
