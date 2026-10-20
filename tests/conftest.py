import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_keitaro
from app.config import Settings, get_settings
from app.db import Base, get_db
from app.keitaro.client import KeitaroClient
from app.main import app
from tests.fake_keitaro import FakeKeitaro


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        keitaro_url="https://kt.test",
        keitaro_api_key="test-key",
        database_url="sqlite://",
    )


@pytest.fixture
def fake() -> FakeKeitaro:
    return FakeKeitaro()


@pytest.fixture
def kt(settings, fake) -> KeitaroClient:
    client = KeitaroClient(settings, transport=fake.transport)
    yield client
    client.close()


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def api(db, kt, settings):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_keitaro] = lambda: kt
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app)
    app.dependency_overrides.clear()
