import logging

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.agents.registry import agent_runtime_services, include_agent_routers
from backend.agents.routes import router as agents_router
from backend.api.auth_routes import router as auth_router
from backend.api.homeassistant_routes import router as homeassistant_router
from backend.api.settings_routes import router as settings_router
from backend.paths import FRONTEND_DIST, LOG_DIR
from backend.services.auth_service import user_from_request


LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / "agent-api.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and "." not in path.rsplit("/", 1)[-1]:
                return await super().get_response("index.html", scope)
            raise

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
app.include_router(homeassistant_router)
app.include_router(agents_router)
include_agent_routers(app)
app.include_router(settings_router)


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
    for service in agent_runtime_services():
        start_scheduler = getattr(service, "start_scheduler", None)
        if callable(start_scheduler):
            start_scheduler()


@app.on_event("shutdown")
def stop_schedulers() -> None:
    for service in agent_runtime_services():
        stop_scheduler = getattr(service, "stop_scheduler", None)
        if callable(stop_scheduler):
            stop_scheduler()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if FRONTEND_DIST.exists():
    app.mount("/", SPAStaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
