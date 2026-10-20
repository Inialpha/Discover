"""Database migrations (Alembic). They live inside the package so they run the same way from any working directory.

  Apply at startup:  done automatically (AUTO_MIGRATE=true, the default)
  By hand:           alembic upgrade head            (from backend/, uses DATABASE_URL)
  After editing models.py:  alembic revision --autogenerate -m "describe the change"   then review the new file in versions/
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Connection

HERE = Path(__file__).parent


def config(connection: Connection | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(HERE))
    if connection is not None:
        cfg.attributes["connection"] = connection  # env.py reuses it instead of opening its own
    return cfg


def upgrade(connection: Connection, revision: str = "head") -> None:
    """Called inside `await conn.run_sync(upgrade)`: migrates the database behind this connection."""
    command.upgrade(config(connection), revision)
