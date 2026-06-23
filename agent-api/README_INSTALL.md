# RoboterSteve Installation

1. Copy `.env.example` to `.env` and adjust credentials.
2. Copy `config.example.yaml` to `config.yaml` and adjust integrations.
3. Install dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

4. Start:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

Runtime data stays in `data/`, `logs/` and `backups/`; those folders are not part of update ZIP payloads.
