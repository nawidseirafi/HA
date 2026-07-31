from fastapi import APIRouter

from backend.services.context import ContextService


router = APIRouter(prefix="/api/context", tags=["context"])
context_service = ContextService()


@router.get("/status")
def context_status():
    return context_service.status()


@router.get("/history")
def context_history(limit: int = 100):
    return context_service.history(limit=limit)


@router.get("/debug")
def context_debug():
    return context_service.debug()
