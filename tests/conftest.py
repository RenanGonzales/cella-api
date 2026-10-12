from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import engine, get_db
from app.main import app


@pytest.fixture
def db() -> Iterator[Session]:
    """Database session wrapped in a transaction that is rolled back after each test.

    Commits inside the app become savepoints, so tests run against a real PostgreSQL
    without leaving any data behind.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def settings() -> Settings:
    return Settings(demo_enabled=True)


@pytest.fixture
def client(db: Session, settings: Settings) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def signup(client: TestClient, email: str, household_name: str = "Home") -> dict[str, str]:
    """Register a user with a new household and return the Authorization header."""
    response = client.post(
        "/auth/register",
        json={
            "name": email.split("@")[0].title(),
            "email": email,
            "password": "correct horse battery",
            "household_name": household_name,
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def owner(client: TestClient) -> dict[str, str]:
    """Headers of a user with a brand-new household (default areas and categories)."""
    return signup(client, "owner@example.com")


@pytest.fixture
def stranger(client: TestClient) -> dict[str, str]:
    """Headers of a user from another household."""
    return signup(client, "stranger@example.com", household_name="Other home")
