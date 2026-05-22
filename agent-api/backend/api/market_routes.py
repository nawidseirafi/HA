from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.agents.market import MarketAgent
from backend.services.market_report_service import MarketReportService


router = APIRouter(prefix="/api/market", tags=["market"])
store = MarketReportService()
agent = MarketAgent()


def payload_dict(payload: BaseModel) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    return payload.dict()


class WatchlistPayload(BaseModel):
    symbol: str
    name: str = ""
    asset_type: Literal["stock", "etf", "crypto", "index"] = "stock"
    exchange: str = ""
    currency: str = "USD"
    notes: str = ""
    enabled: bool = True


@router.get("/watchlist")
def watchlist():
    return {"items": store.watchlist(), "disclaimer": "Keine Finanzberatung."}


@router.post("/watchlist")
def create_watchlist_item(payload: WatchlistPayload):
    try:
        return store.create_watchlist_item(payload_dict(payload))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/watchlist/{item_id}")
def update_watchlist_item(item_id: int, payload: WatchlistPayload):
    try:
        return store.update_watchlist_item(item_id, payload_dict(payload))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/watchlist/{item_id}")
def delete_watchlist_item(item_id: int):
    store.delete_watchlist_item(item_id)
    return {"ok": True}


@router.post("/run")
def run_market_agent():
    return agent.run()


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
        "disclaimer": "Keine Finanzberatung.",
    }


@router.get("/reports/{symbol}/latest")
def latest_report_for_symbol(symbol: str):
    report = store.latest_for_symbol(symbol)
    if not report:
        raise HTTPException(status_code=404, detail="Kein Report vorhanden.")
    return {"report": report, "news": store.news(symbol), "disclaimer": "Keine Finanzberatung."}


@router.get("/summary")
def summary():
    return store.summary()
