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
    """Bring the schema to head via Alembic, auto-adopting any existing DB.

    - fresh DB (no tables)   -> upgrade head (Alembic creates everything)
    - legacy create_all DB   -> stamp head (adopt without recreating)
    - already-migrated DB    -> upgrade head (apply pending migrations)

    Falls back to create_all only if the Alembic tree isn't present.
    """
    import logging  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from sqlalchemy import inspect  # noqa: PLC0415

    logger = logging.getLogger("fleet.db")
    alembic_ini = Path(__file__).resolve().parents[1] / "alembic.ini"

    if not alembic_ini.exists():
        _create_all()
        return

    from alembic.config import Config  # noqa: PLC0415

    from alembic import command  # noqa: PLC0415

    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(alembic_ini.parent / "alembic"))

    insp = inspect(engine)
    if insp.has_table("nodes") and not insp.has_table("alembic_version"):
        logger.info("adopting existing schema into Alembic (stamp head)")
        command.stamp(cfg, "head")
    else:
        command.upgrade(cfg, "head")


def _create_all() -> None:
    from app.models import audit as _audit  # noqa: F401,PLC0415
    from app.models import identity as _identity  # noqa: F401,PLC0415
    from app.models import node as _node  # noqa: F401,PLC0415
    from app.models import provisioning as _prov  # noqa: F401,PLC0415
    from app.models.base import Base  # noqa: PLC0415

    Base.metadata.create_all(bind=engine)
