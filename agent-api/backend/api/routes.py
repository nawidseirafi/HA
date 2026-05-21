import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, UploadFile

from backend.services.invoice_service import InvoiceService, utc_now


BASE_DIR = Path(__file__).resolve().parents[2]
STATUS_PATH = BASE_DIR / "backend" / "storage" / "status.json"

logger = logging.getLogger("agent-api.routes")
router = APIRouter()
invoice_service = InvoiceService()


def default_status() -> dict[str, dict[str, Any]]:
    return {
        "invoices": {"name": "invoices", "status": "idle", "last_run": None, "last_error": None},
        "vacation": {"name": "vacation", "status": "idle", "last_run": None, "last_error": None},
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


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/agents")
def list_agents() -> dict[str, list[str]]:
    return {"agents": ["invoices", "vacation"]}


@router.get("/agents/status")
def agents_status() -> dict[str, dict[str, Any]]:
    return read_status()


@router.post("/agents/invoices/run")
def run_invoices() -> dict[str, Any]:
    update_agent_status("invoices", status="running", last_error=None)
    try:
        result = invoice_service.run_agent()
    except Exception as exc:
        update_agent_status("invoices", status="error", last_error=str(exc))
        raise
    current_status = update_agent_status("invoices", status="idle", last_run=utc_now(), last_error=None)
    return {"agent": "invoices", "status": current_status, "result": result}


@router.post("/agents/invoices/upload")
def upload_invoice(file: UploadFile = File(...)) -> dict[str, Any]:
    result = invoice_service.upload(file)
    return {"agent": "invoices", **result}


@router.post("/agents/vacation/run")
def run_vacation() -> dict[str, Any]:
    current_status = update_agent_status("vacation", status="idle", last_run=utc_now(), last_error=None)
    return {"agent": "vacation", "status": current_status, "result": {"triggered": True}}
