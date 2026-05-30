from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
API_DIR = BACKEND_DIR.parent
PROJECT_DIR = API_DIR.parent
API_CONFIG_PATH = API_DIR / "config.yaml"
FRONTEND_DIST = API_DIR / "frontend" / "dist"
AGENTS_DIR = BACKEND_DIR / "agents"
LOG_DIR = API_DIR / "logs"
ENV_PATH = API_DIR / ".env"