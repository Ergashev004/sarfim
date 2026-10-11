import sqlite3
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from bot.db import models  # noqa: F401
from bot.db.base import Base
from bot.services.categories import DEFAULT_CATEGORIES, FALLBACK_CATEGORY

TABLES = {"users", "categories", "transactions", "user_keywords", "ai_requests"}


def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows} - {"alembic_version"}


def test_upgrade_creates_all_tables(migrated_db, db_path):
    assert _tables(db_path) == TABLES


def test_default_categories_seeded_in_order(migrated_db, db_path):
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name, emoji, user_id FROM categories ORDER BY id").fetchall()
    assert [(n, e) for n, e, _ in rows] == list(DEFAULT_CATEGORIES)
    assert all(user_id is None for *_, user_id in rows)


def test_default_categories_count_and_fallback():
    assert len(DEFAULT_CATEGORIES) == 11
    assert FALLBACK_CATEGORY in {name for name, _ in DEFAULT_CATEGORIES}


def test_transactions_index_exists(migrated_db, db_path):
    with sqlite3.connect(db_path) as conn:
        cols = conn.execute("PRAGMA index_info('ix_transactions_user_id_occurred_on')").fetchall()
    assert [c[2] for c in cols] == ["user_id", "occurred_on"]


def test_models_match_migrations(migrated_db, db_path):
    """Modelni o'zgartirib, migratsiya yozishni unutsak — shu test qizaradi."""
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == []


def test_downgrade_and_upgrade_again(alembic_cfg: Config, db_path):
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "base")
    assert _tables(db_path) == set()

    command.upgrade(alembic_cfg, "head")
    assert _tables(db_path) == TABLES
