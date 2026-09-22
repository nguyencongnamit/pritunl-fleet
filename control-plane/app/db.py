"""SQLAlchemy engine + session management for the control-plane database.

Phase 1 uses create_all() for the lab so it runs with zero migration steps.
Alembic is wired in a later phase for real deployments (see alembic.ini stub).
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()

engine = create_engine(
    str(_settings.database_url),
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped session."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create tables that don't yet exist. Phase-1 convenience only."""
    from app.models import audit as _audit  # noqa: F401,PLC0415
    from app.models import identity as _identity  # noqa: F401,PLC0415
    from app.models import node as _node  # noqa: F401,PLC0415  (register mappers)
    from app.models import provisioning as _prov  # noqa: F401,PLC0415
    from app.models.base import Base  # noqa: PLC0415  (avoid circular import at module load)

    Base.metadata.create_all(bind=engine)
