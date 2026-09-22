"""Aggregate dashboard + cross-site user search."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.read import DashboardOut, ScopedServer, ScopedUser
from app.services import dashboard as dashboard_service

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
async def get_dashboard(db: Session = Depends(get_db)) -> DashboardOut:
    return await dashboard_service.build_dashboard(db)


@router.get("/servers", response_model=list[ScopedServer])
async def list_servers(db: Session = Depends(get_db)) -> list[ScopedServer]:
    return await dashboard_service.list_servers(db)


@router.get("/users", response_model=list[ScopedUser])
async def search_users(
    q: str | None = Query(default=None, description="match on user name or email"),
    db: Session = Depends(get_db),
) -> list[ScopedUser]:
    return await dashboard_service.search_users(db, q)
