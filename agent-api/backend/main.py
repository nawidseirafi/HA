import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.agents.invoices.export_routes import router as export_router
from backend.agents.invoices.routes import router as invoice_router
from backend.agents.market.routes import router as market_router
from backend.agents.mywellness.routes import router as mywellness_router
from backend.api.auth_routes import router as auth_router
from backend.api.settings_routes import router as settings_router
from backend.paths import FRONTEND_DIST, LOG_DIR
from backend.services.auth_service import user_from_request


LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / "agent-api.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="RoboterSteve Agent API",
    description="Lokale API fuer InvoiceAgent, Verwaltung, Exporte und Uploads.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_API_PATHS = {"/health", "/api/auth/login"}


@app.middleware("http")
async def require_api_auth(request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_API_PATHS:
        try:
            user_from_request(request)
        except Exception as exc:
            return JSONResponse({"detail": getattr(exc, "detail", "Nicht angemeldet.")}, status_code=getattr(exc, "status_code", 401))
    return await call_next(request)


app.include_router(auth_router)
app.include_router(invoice_router)
app.include_router(export_router)
app.include_router(mywellness_router)
app.include_router(settings_router)
app.include_router(market_router)


@app.on_event("startup")
def start_schedulers() -> None:
    from backend.agents.mywellness.routes import mywellness_service

    mywellness_service.start_scheduler()


@app.on_event("shutdown")
def stop_schedulers() -> None:
    from backend.agents.mywellness.routes import mywellness_service

    mywellness_service.stop_scheduler()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
