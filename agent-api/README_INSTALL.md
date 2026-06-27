# RoboterSteve Installation

1. Copy `.env.example` to `.env` and adjust credentials.
2. Copy `config.example.yaml` to `config.yaml` and adjust integrations.
3. Install dependencies:

```bash
deactivate
rm -rf .venv
/opt/homebrew/opt/python@3.14/bin/python3.14 -m venv .venv
source .venv/bin/activate      
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8080
```

4. Start:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

Runtime data stays in `data/`, `logs/` and `backups/`; those folders are not part of update ZIP payloads.
