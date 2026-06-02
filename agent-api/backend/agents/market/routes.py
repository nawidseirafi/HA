from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .agent import MarketAgent
from .report_service import MarketReportService


router = APIRouter(prefix="/api/market", tags=["market"])
store = MarketReportService()
agent = MarketAgent()


def payload_dict(payload: BaseModel) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    return payload.dict()


class WatchlistPayload(BaseModel):
    input_name: str | None = None
    symbol: str = ""
    name: str = ""
    resolved_name: str = ""
    isin: str = ""
    wkn: str = ""
    asset_type: Literal["stock", "etf", "fund", "etc", "crypto", "index"] = "stock"
    exchange: str = ""
    currency: str = "USD"
    notes: str = ""
    enabled: bool = True


class SettingsPayload(BaseModel):
    enabled: bool | None = None


@router.get("/status")
def status():
    return agent.status()


@router.post("/enable")
def enable_market_agent():
    return agent.enable()


@router.post("/disable")
def disable_market_agent():
    return agent.disable()


@router.post("/toggle")
def toggle_market_agent():
    return agent.toggle()


@router.put("/settings")
def update_market_settings(payload: SettingsPayload):
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    return agent.update_settings(data)


@router.get("/watchlist")
def watchlist():
    return {"items": store.watchlist(), "disclaimer": "Keine Finanzberatung."}


@router.post("/watchlist")
def create_watchlist_item(payload: WatchlistPayload):
    try:
        return agent.create_watchlist_item(payload_dict(payload))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/watchlist/{item_id}")
def update_watchlist_item(item_id: int, payload: WatchlistPayload):
    try:
        return agent.update_watchlist_item(item_id, payload_dict(payload))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/watchlist/{item_id}")
def delete_watchlist_item(item_id: int):
    store.delete_watchlist_item(item_id)
    return {"ok": True}


@router.get("/watchlist/resolve")
def resolve_watchlist_input(q: str = Query(..., min_length=1)):
    try:
        return {"asset": agent.resolve_asset(q), "disclaimer": "Keine Finanzberatung."}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/run")
def run_market_agent():
    result = agent.run()
    if result.get("run_status") == "completed":
        return {**result, "status": "completed", "current_status": "active"}
    return result


@router.post("/analyze/{symbol}")
def analyze_symbol(symbol: str):
    return agent.analyze_symbol(symbol)


@router.get("/reports")
def reports(
    symbol: Optional[str] = Query(default=None),
    signal: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    return {"reports": store.reports(symbol=symbol, signal=signal, limit=limit), "disclaimer": "Keine Finanzberatung."}


@router.get("/reports/latest")
def latest_reports():
    return {"reports": store.latest_reports(), "disclaimer": "Keine Finanzberatung."}


@router.get("/reports/{symbol}")
def reports_for_symbol(symbol: str, limit: int = Query(default=100, ge=1, le=500)):
    return {
        "reports": store.reports(symbol=symbol, limit=limit),
        "news": store.news(symbol),
        "signal_history": store.signal_history(symbol, limit=limit),
        "disclaimer": "Keine Finanzberatung.",
    }


@router.get("/signals/{symbol}/history")
def signal_history(symbol: str, limit: int = Query(default=50, ge=1, le=200)):
    return {"history": store.signal_history(symbol, limit=limit), "disclaimer": "Keine Finanzberatung."}


@router.get("/reports/{symbol}/latest")
def latest_report_for_symbol(symbol: str):
    report = store.latest_for_symbol(symbol)
    if not report:
        raise HTTPException(status_code=404, detail="Kein Report vorhanden.")
    return {"report": report, "news": store.news(symbol), "disclaimer": "Keine Finanzberatung."}


@router.get("/summary")
def summary():
    return {**store.summary(), "agent": agent.status()}
