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
from backend.files.entrypoints.web import files as files_web
from backend.identity.entrypoints.web import admin as identity_admin
from backend.identity.entrypoints.web import auth as identity_auth
from backend.identity.entrypoints.web import me as identity_me
from backend.orchestrators import ports as cross_ports
from backend.projects.entrypoints.web import projects as projects_web
from backend.teaching.entrypoints.web import _dependencies as teaching_deps
from backend.teaching.entrypoints.web import courses as teaching_courses
from backend.teaching.entrypoints.web import labs as teaching_labs
from backend.teaching.entrypoints.web import submissions as teaching_submissions

ROOT_PATH = "/labdigital/api"
API_PREFIX = "/v1"
# 2 MB de contenido de proyecto + margen de JSON/escapes. nginx limita también.
MAX_BODY_BYTES = 3 * 1024 * 1024
# `POST /v1/files`: 25 MB por archivo + margen del multipart (el servicio corta a 25 MB).
MAX_UPLOAD_BODY_BYTES = 25 * 1024 * 1024 + 256 * 1024

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
    app.add_middleware(
        middleware.BodySizeLimitMiddleware,
        max_bytes=MAX_BODY_BYTES,
        overrides={("POST", f"{API_PREFIX}/files"): MAX_UPLOAD_BODY_BYTES},
    )
    app.add_middleware(middleware.RequestLoggingMiddleware)
    exception_handler.install(app)

    v1 = fastapi.APIRouter(prefix=API_PREFIX)
    v1.include_router(identity_auth.router)
    v1.include_router(identity_auth.wellknown_router)
    v1.include_router(identity_me.router)
    v1.include_router(identity_admin.router)
    v1.include_router(projects_web.router)
    v1.include_router(teaching_courses.router)
    v1.include_router(teaching_labs.router)
    v1.include_router(teaching_submissions.router)
    v1.include_router(files_web.router)

    # Puertos entre productos (ver `backend.orchestrators.ports`).
    app.dependency_overrides[teaching_deps.get_user_directory] = cross_ports.IdentityUserDirectory
    app.dependency_overrides[teaching_deps.get_projects_port] = cross_ports.ProjectsAdapter
    app.dependency_overrides[teaching_deps.get_files_port] = cross_ports.FilesAdapter
    app.dependency_overrides[files_web.get_access_policy] = cross_ports.TeachingBlobAccessPolicy

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
