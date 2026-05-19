import logging
from pathlib import Path

from fastapi import FastAPI

from api.routes import router


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / "agent-api.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Local Agent API",
    description="Zentrale API zum Starten lokaler Agenten und Hochladen von Dateien.",
    version="0.1.0",
)

app.include_router(router)
