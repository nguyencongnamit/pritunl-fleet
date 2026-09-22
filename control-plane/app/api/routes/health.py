"""Control-plane self health endpoints (not node health — that's under /nodes)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db

router = APIRouter(tags=["meta"])


@router.get("/healthz")
def healthz() -> dict:
    """Liveness — the process is up."""
    return {"status": "ok"}


@router.get("/readyz")
def readyz(db: Session = Depends(get_db)) -> dict:
    """Readiness — the control-plane database is reachable."""
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}
