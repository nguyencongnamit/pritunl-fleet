"""FastAPI application factory for the Pritunl Fleet control plane."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.deps import rbac_guard
from app.api.routes import actions as action_routes
from app.api.routes import auth as auth_routes
from app.api.routes import dashboard as dashboard_routes
from app.api.routes import health as health_routes
from app.api.routes import nodes as node_routes
from app.api.routes import principals as principal_routes
from app.api.routes import provisioning as provisioning_routes
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.services.auth import bootstrap_admin
from app.services.health import run_health_loop
from app.services.sync import run_sync_loop

logger = logging.getLogger("fleet")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    logger.info("starting control plane (env=%s)", settings.environment)

    # Phase-1 convenience: ensure tables exist. Real deploys use Alembic.
    init_db()

    # First-run admin (no-op if principals already exist or bootstrap unset).
    session = SessionLocal()
    try:
        bootstrap_admin(session)
    finally:
        session.close()

    stop_event = asyncio.Event()
    health_task = asyncio.create_task(run_health_loop(stop_event))
    sync_task = asyncio.create_task(run_sync_loop(stop_event, settings.sync_sweep_interval))
    try:
        yield
    finally:
        stop_event.set()
        for task in (health_task, sync_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("control plane stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Pritunl Fleet — Control Plane",
        version="0.1.0",
        description="Multi-site management control plane for Pritunl OSS.",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def security_headers(request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Cache-Control", "no-store")
        return resp
    # Unauthenticated: liveness/readiness + auth (login/MFA) endpoints.
    app.include_router(health_routes.router)
    app.include_router(auth_routes.router, prefix="/api/v1")

    # Everything else requires a full-scope token; rbac_guard enforces roles.
    guarded = [Depends(rbac_guard)]
    app.include_router(node_routes.router, prefix="/api/v1", dependencies=guarded)
    app.include_router(dashboard_routes.router, prefix="/api/v1", dependencies=guarded)
    app.include_router(action_routes.router, prefix="/api/v1", dependencies=guarded)
    app.include_router(provisioning_routes.router, prefix="/api/v1", dependencies=guarded)
    app.include_router(principal_routes.router, prefix="/api/v1", dependencies=guarded)

    # Serve the built SPA (if present) at the root. API routes above take
    # precedence; this mount only catches unmatched paths. Absent in pure-API
    # local dev, where the Vite dev server proxies /api instead.
    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="spa")

    return app


app = create_app()
