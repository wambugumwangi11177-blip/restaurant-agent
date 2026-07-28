from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy import text

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
import os
import sys
from dotenv import load_dotenv

# Add the backend/ directory to sys.path so we can import models directly —
# matching the plain `import models` convention used everywhere else in this
# codebase (main.py, routers/*.py, etc.), NOT `from backend.models import`.
#
# The previous version assumed a wrapping repo_root/backend/ layout (3 levels
# up from this file) and did `from backend.models import Base`. That works
# when running locally with cwd inside backend/ (there's a real repo root
# above it), but breaks inside the deployed Docker container: the Dockerfile's
# build context IS backend/, so WORKDIR /app contains models.py directly —
# there is no wrapping "backend" package at all in the container, causing
# `ModuleNotFoundError: No module named 'backend'` on every real deploy
# (found 2026-07-07, Railway crash log). Only 2 levels up (env.py -> alembic
# -> backend/, or /app in the container) is correct in both environments.
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)

from models import Base
target_metadata = Base.metadata

load_dotenv()
# Override sqlalchemy.url with env var
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def _ensure_wide_version_column(connection) -> None:
    """
    Alembic hardcodes alembic_version.version_num to VARCHAR(32) — see
    alembic/ddl/impl.py's version_table_impl, `Column("version_num",
    String(32), ...)`, not configurable via context.configure(). Several of
    this repo's own revision ids already exceed that (e.g.
    "025_tenant_fk_and_owner_phone_integrity" is 39 chars; 8 of the 25
    revisions in versions/ are over 32).

    Found 2026-07-28 running `alembic upgrade head` against a genuinely fresh
    Postgres database (the exact restore-drill / new-environment scenario
    docs/external-hardening-checklist.md flags as never verified): it crashes
    with StringDataRightTruncation partway through the very first upgrade
    (migration 002's revision id doesn't fit). Because this file wraps every
    migration in one outer transaction (see run_migrations_online below),
    that failure rolled back the ENTIRE transaction — including the
    alembic_version table's own creation — so a fresh Postgres could never
    successfully bootstrap via `alembic upgrade head` at all. Any new Railway
    preview/branch environment or a real disaster-recovery restore into a
    blank database would crash-loop on this before ever reaching migration 003.

    Only Postgres needs this: SQLite doesn't enforce VARCHAR length, so
    migrations already ran fine there (which is exactly why this went
    unnoticed — the test suite is SQLite-only, see tests/conftest.py).
    """
    if connection.dialect.name != "postgresql":
        return
    connection.execute(text(
        "CREATE TABLE IF NOT EXISTS alembic_version ("
        "  version_num VARCHAR(255) NOT NULL, "
        "  CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)"
        ")"
    ))
    connection.execute(text(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    ))
    connection.commit()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _ensure_wide_version_column(connection)

        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
