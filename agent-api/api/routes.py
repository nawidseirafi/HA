import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from fastapi import APIRouter, File, HTTPException, UploadFile

from agents.invoices import InvoiceAgent
from agents.vacation import VacationAgent


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"
STATUS_PATH = BASE_DIR / "storage" / "status.json"
INVOICE_UPLOAD_DIR = BASE_DIR / "storage" / "uploads" / "invoices"

logger = logging.getLogger("agent-api.routes")
router = APIRouter()


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file) or {}


config = load_config()
agents = {
    "invoices": InvoiceAgent(config=config.get("agents", {}).get("invoices", {})),
    "vacation": VacationAgent(config=config.get("agents", {}).get("vacation", {})),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_status() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "name": name,
            "status": "idle",
            "last_run": None,
            "last_error": None,
        }
        for name in agents
    }


def read_status() -> dict[str, dict[str, Any]]:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STATUS_PATH.exists():
        status = default_status()
        write_status(status)
        return status

    try:
        with STATUS_PATH.open("r", encoding="utf-8") as status_file:
            status = json.load(status_file)
    except (json.JSONDecodeError, OSError):
        logger.exception("Could not read status file, resetting status.")
        status = {}

    merged = default_status()
    for name, agent_status in status.items():
        if name in merged and isinstance(agent_status, dict):
            merged[name].update(agent_status)
    return merged


def write_status(status: dict[str, dict[str, Any]]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATUS_PATH.open("w", encoding="utf-8") as status_file:
        json.dump(status, status_file, indent=2)


def update_agent_status(agent_name: str, **updates: Any) -> dict[str, Any]:
    status = read_status()
    status[agent_name].update(updates)
    write_status(status)
    return status[agent_name]


def run_agent(agent_name: str) -> dict[str, Any]:
    agent = agents[agent_name]
    update_agent_status(agent_name, status="running", last_error=None)

    try:
        result = agent.run()
    except Exception as exc:
        logger.exception("Agent run failed: %s", agent_name)
        update_agent_status(agent_name, status="error", last_error=str(exc))
        raise HTTPException(status_code=500, detail=f"{agent_name} agent failed") from exc

    current_status = update_agent_status(
        agent_name,
        status="idle",
        last_run=utc_now(),
        last_error=None,
    )
    return {"agent": agent_name, "status": current_status, "result": result}


def secure_filename(filename: str) -> str:
    path_name = Path(filename).name
    stem = Path(path_name).stem.strip().lower()
    suffix = Path(path_name).suffix.lower()

    safe_stem = re.sub(r"[^a-z0-9._-]+", "_", stem)
    safe_stem = safe_stem.strip("._-") or "upload"
    safe_suffix = suffix if re.fullmatch(r"\.[a-z0-9]{1,12}", suffix) else ""

    return f"{safe_stem}{safe_suffix}"


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/agents")
def list_agents() -> dict[str, list[str]]:
    return {"agents": list(agents.keys())}


@router.get("/agents/status")
def agents_status() -> dict[str, dict[str, Any]]:
    return read_status()


@router.post("/agents/invoices/run")
def run_invoices() -> dict[str, Any]:
    return run_agent("invoices")


@router.post("/agents/invoices/upload")
def upload_invoice(file: UploadFile = File(...)) -> dict[str, Any]:
    INVOICE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    safe_name = secure_filename(file.filename or "upload")
    stored_name = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex}-{safe_name}"
    destination = INVOICE_UPLOAD_DIR / stored_name

    with destination.open("wb") as output_file:
        shutil.copyfileobj(file.file, output_file)

    logger.info("Invoice upload stored: %s", destination)
    return {
        "status": "uploaded",
        "agent": "invoices",
        "filename": safe_name,
        "stored_filename": stored_name,
        "path": str(destination.relative_to(BASE_DIR)),
    }


@router.post("/agents/vacation/run")
def run_vacation() -> dict[str, Any]:
    return run_agent("vacation")
