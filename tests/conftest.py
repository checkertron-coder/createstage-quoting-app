"""
Shared test fixtures — in-memory SQLite database, test client, auth helpers.
"""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set JWT_SECRET before importing app modules
os.environ["JWT_SECRET"] = "test-secret-key-for-testing-only"
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from backend.database import Base, get_db
from backend.main import app


# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_database():
    """Create all tables before each test, drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def db():
    """Direct database session for test setup/assertions."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_headers(client):
    """Register a test user and return auth headers."""
    response = client.post("/api/auth/register", json={
        "email": "test@fabricator.com",
        "password": "strongpassword123",
    })
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def guest_headers(client):
    """Create a guest user and return auth headers."""
    response = client.post("/api/auth/guest")
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
