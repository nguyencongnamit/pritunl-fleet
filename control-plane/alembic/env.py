"""Alembic environment — targets the app's SQLAlchemy metadata, URL from settings."""

from __future__ import annotations

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.config import get_settings
from app.models import audit as _audit  # noqa: F401  register mappers
from app.models import identity as _identity  # noqa: F401
from app.models import node as _node  # noqa: F401
from app.models import provisioning as _prov  # noqa: F401
from app.models.base import Base

config = context.config
config.set_main_option("sqlalchemy.url", str(get_settings().database_url))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(get_settings().database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
