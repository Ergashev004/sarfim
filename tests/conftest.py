from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import time_machine
from alembic import command
from alembic.config import Config

from bot.db import repo
from bot.db.models import User
from bot.db.session import make_engine, make_sessionmaker
from tests.fakes import make_state

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


@pytest.fixture
def frozen_time():
    """2026-10-11 12:00, Toshkent. Modulda: pytestmark = pytest.mark.usefixtures("frozen_time")."""
    tz = ZoneInfo("Asia/Tashkent")
    with time_machine.travel(datetime(2026, 10, 11, 12, 0, tzinfo=tz), tick=False):
        yield


@pytest.fixture
async def me(session) -> User:
    user = await repo.get_or_create_user(session, 1001, "Akobir")
    await session.commit()
    return user


@pytest.fixture
async def stranger(session) -> User:
    user = await repo.get_or_create_user(session, 2002, "Begona")
    await session.commit()
    return user


@pytest.fixture
def state():
    return make_state(1001)
