"""FastAPI application entrypoint with request-id error contract (plan §12.1)."""
from __future__ import annotations

import logging
import os
import threading
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routers import alerts, analysis, auth, cases, models, reports, uploads
from app.config.settings import get_settings
from app.db.migrate import init_db

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("xai.api")


def create_app() -> FastAPI:
    settings = get_settings()
    settings.ensure_dirs()
    init_db()

    app = FastAPI(title="XAI-Insider API", version="1.0.0",
                  description="Explainable AI for insider threat detection - lab demonstrator")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        logger.info("%s %s -> %s rid=%s", request.method, request.url.path,
                    response.status_code, rid)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={
            "code": exc.status_code, "message": str(exc.detail),
            "request_id": getattr(request.state, "request_id", None)})

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={
            "code": 422, "message": "validation error",
            "request_id": getattr(request.state, "request_id", None),
            "field_errors": exc.errors()})

    prefix = "/api/v1"
    app.include_router(auth.router, prefix=prefix, tags=["auth"])
    app.include_router(uploads.router, prefix=prefix, tags=["ingestion"])
    app.include_router(analysis.router, prefix=prefix, tags=["analysis"])
    app.include_router(alerts.router, prefix=prefix, tags=["alerts"])
    app.include_router(cases.router, prefix=prefix, tags=["cases"])
    app.include_router(reports.router, prefix=prefix, tags=["reports"])
    app.include_router(models.router, prefix=prefix, tags=["models"])

    # Embedded worker for single-process local demos. In Docker Compose a dedicated
    # worker service runs instead (EMBEDDED_WORKER=false).
    if settings.embedded_worker and os.environ.get("EMBEDDED_WORKER", "").lower() != "false":
        import time
        from app.worker import process_one

        def _loop():
            while True:
                try:
                    if not process_one():
                        time.sleep(settings.worker_poll_seconds)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("embedded worker error: %s", exc)
                    time.sleep(settings.worker_poll_seconds)

        threading.Thread(target=_loop, daemon=True, name="embedded-worker").start()

    return app


app = create_app()