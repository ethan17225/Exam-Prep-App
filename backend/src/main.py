import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import configure_mappers

import src.models  # noqa: F401  — populates Base.metadata; see src/models.py
from src.admin.router import router as admin_router
from src.attempts.router import history_router, progress_router, submit_router
from src.auth.dependencies import make_static_mount_guard
from src.auth.router import router as auth_router
from src.config import SHOW_DOCS_IN, settings
from src.courses.router import router as courses_router
from src.database import SessionDep
from src.documents.config import documents_settings
from src.documents.constants import DOCS_URL_PREFIX
from src.documents.router import router as documents_router
from src.exams.config import exams_settings
from src.exams.constants import UPLOADS_URL_PREFIX
from src.exams.router import questions_router
from src.exams.router import router as exams_router

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("mcq")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Relationship targets are resolved lazily by name, so a model module missing
    # from src/models.py would otherwise fail on the first query instead of here.
    configure_mappers()
    yield


app_kwargs = {"title": "MCQ Exam API", "lifespan": lifespan}
if settings.environment not in SHOW_DOCS_IN:
    app_kwargs["openapi_url"] = None  # also disables /docs and /redoc

app = FastAPI(**app_kwargs)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log the traceback and answer with JSON.

    Starlette's default 500 is bare text/plain emitted outside CORSMiddleware,
    so the frontend's `err.error.detail` read comes back undefined and
    cross-origin callers see an opaque CORS error instead.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # Must stay False while allow_origins is "*" — browsers reject the
    # combination. Prod is same-origin behind nginx and dev is same-origin
    # through proxy.conf.json, so the auth cookie is never cross-origin.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# StaticFiles raises at construction if the directory is missing, so these have
# to exist before the mounts — and they must not be created at config-import
# time, which would be a filesystem side effect on every import.
documents_settings.root.mkdir(parents=True, exist_ok=True)
exams_settings.uploads_dir.mkdir(parents=True, exist_ok=True)

app.mount(DOCS_URL_PREFIX, StaticFiles(directory=str(documents_settings.root)), name="docs-files")
# Question images sit under /api/... so the dev proxy and nginx forward them.
app.mount(UPLOADS_URL_PREFIX, StaticFiles(directory=str(exams_settings.uploads_dir)), name="uploads")

# Dependencies do not apply to mounts, but middleware runs before routing.
app.middleware("http")(make_static_mount_guard([DOCS_URL_PREFIX, UPLOADS_URL_PREFIX]))


class HealthOut(BaseModel):
    status: str


@app.get(
    "/healthz",
    response_model=HealthOut,
    tags=["health"],
    summary="Readiness probe",
    description="Checks the database through the connection pool. Used by the Docker healthcheck.",
    responses={503: {"model": HealthOut, "description": "Database unreachable"}},
)
async def healthz(db: SessionDep):
    # Deliberately touches the pool: pool exhaustion, not process death, is the
    # likely failure mode here. Note there is no /api prefix — the Dockerfile
    # HEALTHCHECK and the frontend's depends_on both hit this exact path.
    try:
        await db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any DB failure means not ready
        logger.exception("Health check failed")
        return JSONResponse({"status": "unhealthy"}, status_code=503)
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(courses_router)
app.include_router(documents_router)
app.include_router(exams_router)
app.include_router(questions_router)
app.include_router(submit_router)
app.include_router(progress_router)
app.include_router(history_router)
app.include_router(admin_router)
