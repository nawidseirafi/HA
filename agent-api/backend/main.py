from importlib import import_module
import os

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.agents.registry import agent_runtime_services, include_agent_routers
from backend.agents.routes import router as agents_router
from backend.logging_config import configure_logging
from backend.paths import FRONTEND_DIST
from backend.product import active_product, is_core_service_enabled
from backend.services.auth_service import user_from_request
from backend.services.messaging.routes import router as messaging_router


configure_logging()


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and "." not in path.rsplit("/", 1)[-1]:
                response = await super().get_response("index.html", scope)
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                return response
            raise
        if path in {"", ".", "/", "index.html"} or "." not in path.rsplit("/", 1)[-1]:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        elif path.startswith("assets/"):
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        return response

app = FastAPI(
    title="RoboterSteve Agent API",
    description="Lokale API fuer InvoiceAgent, Verwaltung, Exporte und Uploads.",
    version="0.2.0",
    swagger_ui_parameters={"persistAuthorization": True},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_API_PATHS = {"/health", "/api/auth/login", "/api/product"}
MONITOR_ONLY = os.getenv("ROBOTERSTEVE_MONITOR_ONLY", "0") == "1"


@app.middleware("http")
async def require_api_auth(request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_API_PATHS:
        try:
            user_from_request(request)
        except Exception as exc:
            return JSONResponse({"detail": getattr(exc, "detail", "Nicht angemeldet.")}, status_code=getattr(exc, "status_code", 401))
    if MONITOR_ONLY and path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"} and path not in {"/api/auth/login", "/api/home-hub/chat", "/api/home-hub/conversation"}:
        return JSONResponse({"detail": "Beobachtungsmodus: Aktionen sind deaktiviert."}, status_code=403)
    return await call_next(request)


def include_core_router(service_id: str, module_name: str) -> None:
    if not is_core_service_enabled(service_id):
        return
    module = import_module(module_name)
    router = getattr(module, "router", None)
    if router is not None:
        app.include_router(router)


include_core_router("auth", "backend.api.auth_routes")
include_core_router("system", "backend.api.system_routes")
include_core_router("household", "backend.api.household_routes")
include_core_router("infrastructure", "backend.api.infrastructure_routes")
include_core_router("homeassistant", "backend.api.homeassistant_routes")
include_core_router("homeassistant", "backend.api.home_hub_routes")
include_core_router("context", "backend.api.context_routes")
include_core_router("orchestrator", "backend.api.orchestrator_routes")
include_core_router("waste", "backend.api.waste_routes")
app.include_router(agents_router)
include_core_router("messaging", "backend.services.messaging.routes")
include_agent_routers(app)
include_core_router("settings", "backend.api.settings_routes")


@app.get("/api/product")
def product_info() -> dict[str, object]:
    return active_product().public_dict()


SECURITY_SCHEME_NAME = "BearerAuth"


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    components = schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes[SECURITY_SCHEME_NAME] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "JWT aus POST /api/auth/login als Bearer Token verwenden.",
    }
    for path, methods in schema.get("paths", {}).items():
        if not path.startswith("/api/") or path in PUBLIC_API_PATHS:
            continue
        for operation in methods.values():
            if isinstance(operation, dict):
                operation.setdefault("security", [{SECURITY_SCHEME_NAME: []}])
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.on_event("startup")
def start_schedulers() -> None:
    if is_core_service_enabled("homeassistant"):
        from backend.services.home_hub.service import HomeHub
        HomeHub.default().start(dispatch_notifications=not MONITOR_ONLY)
    if MONITOR_ONLY:
        return
    for service in agent_runtime_services():
        start_scheduler = getattr(service, "start_scheduler", None)
        if callable(start_scheduler):
            start_scheduler()


@app.on_event("shutdown")
def stop_schedulers() -> None:
    from backend.services.home_hub.service import HomeHub
    if HomeHub._instance is not None:
        HomeHub._instance.stop()
    for service in agent_runtime_services():
        stop_scheduler = getattr(service, "stop_scheduler", None)
        if callable(stop_scheduler):
            stop_scheduler()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if FRONTEND_DIST.exists():
    app.mount("/", SPAStaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
