from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from bot.db.session import make_engine, make_sessionmaker

ALEMBIC_DIR = Path(__file__).resolve().parents[1] / "alembic"


def make_alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def alembic_cfg(db_path: Path) -> Config:
    return make_alembic_config(f"sqlite+aiosqlite:///{db_path}")


@pytest.fixture
def migrated_db(alembic_cfg: Config) -> str:
    """Haqiqiy migratsiyalar orqali yaratilgan baza (standart kategoriyalar bilan)."""
    command.upgrade(alembic_cfg, "head")
    return alembic_cfg.get_main_option("sqlalchemy.url")


@pytest.fixture
async def sessionmaker(migrated_db: str):
    engine = make_engine(migrated_db)
    yield make_sessionmaker(engine)
    await engine.dispose()


@pytest.fixture
async def session(sessionmaker):
    async with sessionmaker() as s:
        yield s
