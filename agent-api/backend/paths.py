from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
API_DIR = BACKEND_DIR.parent
PROJECT_DIR = API_DIR.parent
AI_AGENT_DIR = PROJECT_DIR / "ai-agent"
API_CONFIG_PATH = API_DIR / "config.yaml"
FRONTEND_DIST = API_DIR / "frontend" / "dist"
LOG_DIR = API_DIR / "logs"
