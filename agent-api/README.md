# RoboterSteve Agent API und Agent Console

Lokale FastAPI-Schnittstelle und React-Weboberflaeche fuer lokale Agenten. Der Rechnungs-Agent ist der erste aktive Bereich; weitere Agenten koennen als eigene Bereiche ergaenzt werden.

## Entwicklung

## Struktur

```text
agent-api/
├── backend/
│   ├── main.py              # FastAPI-App + Router-Registrierung (Uvicorn-Entry)
│   ├── auth/                # Login, JWT
│   ├── settings/            # Diagnose/Konfiguration
│   ├── invoice/             # Rechnungs-API + Export
│   ├── market/              # Boersen-API (ruft ai-agent/market/market.py)
│   └── mywellness/          # Booking-API (ruft ai-agent/mywellness/mywellness.py)
├── frontend/
│   └── src/                 # React + Vite UI
├── logs/
├── config.yaml
└── requirements.txt
```

Die eigentliche Domaenenlogik der Agenten liegt unter `../ai-agent/`. Das Backend importiert Read-Module direkt via `sys.path` und startet schwere Laeufe per `subprocess` ueber die CLIs unter `../ai-agent/<domain>/<domain>.py` (z.B. `mywellness/mywellness.py`, `market/market.py`, `invoice/invoices.py`).

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

## Auth

Alle `/api/*`-Endpunkte ausser `/api/auth/login` sind per JWT geschuetzt. Zugangsdaten werden ueber ENV gesetzt:

```text
AGENT_API_USERNAME
AGENT_API_PASSWORD
AGENT_API_JWT_SECRET
```

Lokaler Fallback fuer Entwicklung ist `admin` / `admin`. `AGENT_API_JWT_SECRET` sollte fuer echte Nutzung gesetzt werden.

## API

Auth-Endpunkte:

```text
POST /api/auth/login
GET  /api/auth/me
```

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

MyWellness-Endpunkte:

```text
GET  /api/agent/status
POST /api/agent/start
POST /api/agent/stop
GET  /api/mywellness/courses
GET  /api/mywellness/courses/upcoming
POST /api/mywellness/book
POST /api/mywellness/cancel
GET  /api/mywellness/bookings
GET  /api/mywellness/logs
```

`POST /api/agent/start` startet den bestehenden `../ai-agent/mywellness/mywellness.py` standardmaessig im `prepare`-Modus, damit Kursdaten aktualisiert werden. Fuer einen Buchungslauf kann optional `{"mode":"book"}` gesendet werden. Persistenter Zustand (Settings, History) liegt in der SQLite-DB `../ai-agent/data/mywellness/mywellness.db`, der Lauf-Status (`is_running`, letzter Output, Kurs-Cache) wird ausschliesslich im Arbeitsspeicher gehalten. Agent-Logs bleiben bei `../ai-agent/mywellness/mywellness.log`.

`GET /api/mywellness/courses/upcoming` liefert das einheitliche Course-Modell fuer die naechsten 48 Stunden. `POST /api/mywellness/book` und `POST /api/mywellness/cancel` erwarten `{"courseId":"..."}` und fuehren Buchung oder Stornierung ausschliesslich ueber das Backend aus.

Uploads fuer Rechnungen werden in der Invoice-Inbox `../ai-agent/data/invoices/inbox` gespeichert. Die React-App startet nach dem Login auf einer neutralen Agenten-Uebersicht; der Rechnungs-Agent liegt unter `/invoices`. Die React-App greift nicht direkt auf SQLite oder Dateien zu, sondern nur ueber FastAPI.

## MyWellness Agent

Der MyWellness-Bereich liegt im Frontend unter `/mywellness`. Angezeigt werden Laufstatus, letzter erfolgreicher Lauf, naechster geplanter Lauf, Fehler, aktuelle Buchungen aus Agent-Daten, gefundene Kurse aus dem Prepare-Cache, verfuegbare Kurse der naechsten 48 Stunden und die letzten Logs. Die Buttons starten den Agenten, deaktivieren/stoppen ihn lokal, laden API-Daten neu oder buchen/stornieren Kurse. Verfuegbare Kurse, Buchungen und Status werden automatisch alle 30 Sekunden aktualisiert.

Erforderliche ENV-Werte werden aus der Umgebung oder aus `../ai-agent/.env` gelesen:

```text
MY_WELLNESS_TOKEN
MY_WELLNESS_USER_ID
MY_WELLNESS_FACILITY_ID
```

Die Kursnamen, der Suchhorizont und die geplanten Laufzeiten stehen in `agent-api/config.yaml` unter `agents.mywellness`. Zugangsdaten werden nicht ans Frontend geliefert. `mywellness_cache.json` bleibt nur noch als Fallback fuer alte Skript-Laeufe; das Dashboard liest vorbereitete Kurse bevorzugt aus `../ai-agent/data/mywellness/mywellness.db`.

Fehler pruefen:

```bash
cd agent-api
../venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload
```

Dann `http://localhost:8080/docs` oder `/mywellness` im Frontend oeffnen. Detailfehler stehen in der DB-Tabelle `mywellness_logs` (`../ai-agent/data/mywellness/mywellness.db`), in `../ai-agent/mywellness/mywellness.log` und im UI-Panel "Agent Logs".

## Hinweise

- Kein Login-System in V1.
- API-Key/Auth ist als naechster Backend-Middleware-Schritt vorbereitet.
- ELSTER-Direktversand ist nicht implementiert und wird nur als deaktivierter Platzhalter angezeigt.
- Steuerkategorien sind nur Datenfelder, keine Steuerberatung.
