"""Aplicación FastAPI única de LabDigital (raíz de composición web).

Desplegada con uvicorn en Docker (no Lambda/Mangum): un solo proceso sirve todos los
contextos. `root_path="/labdigital/api"` porque nginx la publica en
`https://gideam.unimagdalena.edu.co/labdigital/api/`; las rutas viven bajo `/v1`. Starlette
acepta tanto `/v1/...` (nginx quitando el prefijo) como `/labdigital/api/v1/...`.
"""

import fastapi
from fastapi import responses, status
import sqlalchemy as sa

from backend.commons.adapters import engine, logs
from backend.commons.adapters.api import exception_handler, middleware
from backend.identity.entrypoints.web import auth as identity_auth
from backend.identity.entrypoints.web import me as identity_me
from backend.projects.entrypoints.web import projects as projects_web

ROOT_PATH = "/labdigital/api"
API_PREFIX = "/v1"
# 2 MB de contenido de proyecto + margen de JSON/escapes. nginx limita también.
MAX_BODY_BYTES = 3 * 1024 * 1024

_LOGGER = logs.get_logger()


def create_app() -> fastapi.FastAPI:
    app = fastapi.FastAPI(
        title="LabDigital GIDEAM API",
        version="1.0.0",
        root_path=ROOT_PATH,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
    )
    # Orden: el último añadido es el más externo.
    app.add_middleware(middleware.CsrfMiddleware)
    app.add_middleware(middleware.BodySizeLimitMiddleware, max_bytes=MAX_BODY_BYTES)
    app.add_middleware(middleware.RequestLoggingMiddleware)
    exception_handler.install(app)

    v1 = fastapi.APIRouter(prefix=API_PREFIX)
    v1.include_router(identity_auth.router)
    v1.include_router(identity_auth.wellknown_router)
    v1.include_router(identity_me.router)
    v1.include_router(projects_web.router)

    @v1.get("/health", tags=["health"])
    def health() -> responses.JSONResponse:
        """`{ok: true}` (contrato §4); 503 si Postgres no responde."""
        try:
            with engine.get_engine().connect() as connection:
                connection.execute(sa.text("SELECT 1"))
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Health: Postgres no disponible")
            return responses.JSONResponse(
                {"ok": False}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        return responses.JSONResponse({"ok": True})

    app.include_router(v1)
    return app


app = create_app()
