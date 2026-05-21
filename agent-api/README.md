# RoboterSteve Agent API und Agent Console

Lokale FastAPI-Schnittstelle und React-Weboberflaeche fuer lokale Agenten. Der Rechnungs-Agent ist der erste aktive Bereich; weitere Agenten koennen als eigene Bereiche ergaenzt werden.

## Entwicklung

## Struktur

```text
agent-api/
├── backend/
│   ├── main.py
│   ├── api/
│   ├── services/
│   └── storage/
├── frontend/
│   └── src/
├── logs/
├── config.yaml
├── main.py
└── requirements.txt
```

`main.py` im Root bleibt als kleiner Kompatibilitaets-Einstieg fuer `uvicorn main:app`. Der eigentliche Backend-Code liegt unter `backend/`.

Backend:

```bash
cd agent-api
../venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload
```

Frontend:

```bash
cd agent-api/frontend
npm install
npm run dev
```

Danach:

```text
Frontend: http://localhost:5173
Backend:  http://localhost:8080
Swagger:  http://localhost:8080/docs
```

Im lokalen Netzwerk ist Vite je nach Host-IP z.B. unter `http://192.168.178.143:5173` erreichbar.

## Produktion

```bash
cd agent-api/frontend
npm run build

cd ..
../venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

Wenn `frontend/dist` existiert, liefert FastAPI die gebaute React-App direkt aus.

## API

Neue Invoice-Endpunkte:

```text
GET    /api/invoices/summary
GET    /api/invoices/years
GET    /api/invoices/years/{year}
GET    /api/invoices/years/{year}/months/{month}
GET    /api/invoices/{invoice_id}
GET    /api/invoices/{invoice_id}/file
PUT    /api/invoices/{invoice_id}
POST   /api/invoices/{invoice_id}/reanalyze
POST   /api/invoices/{invoice_id}/mark-reviewed
DELETE /api/invoices/{invoice_id}
POST   /api/invoices/upload
POST   /api/invoices/run
```

Export-Endpunkte:

```text
GET /api/exports/year/{year}/excel
GET /api/exports/year/{year}/pdf
GET /api/exports/year/{year}/zip
GET /api/exports/month/{year}/{month}/excel
GET /api/exports/month/{year}/{month}/pdf
GET /api/exports/month/{year}/{month}/zip
```

Kompatible alte Endpunkte bleiben aktiv:

```text
GET  /health
GET  /agents
GET  /agents/status
POST /agents/invoices/run
POST /agents/invoices/upload
POST /agents/vacation/run
```

Uploads fuer Rechnungen werden in der Invoice-Inbox `../ai-agent/data/invoices/inbox` gespeichert. Der Agent-Status liegt unter `backend/storage/status.json`. Die React-App startet nach dem Login auf einer neutralen Agenten-Uebersicht; der Rechnungs-Agent liegt unter `/invoices`. Die React-App greift nicht direkt auf SQLite oder Dateien zu, sondern nur ueber FastAPI.

## Hinweise

- Kein Login-System in V1.
- API-Key/Auth ist als naechster Backend-Middleware-Schritt vorbereitet.
- ELSTER-Direktversand ist nicht implementiert und wird nur als deaktivierter Platzhalter angezeigt.
- Steuerkategorien sind nur Datenfelder, keine Steuerberatung.
