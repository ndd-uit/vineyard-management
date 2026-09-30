import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.auth import get_current_user
from app.main import app
from app import models  # noqa: F401 - register all tables for the isolated SQLite test


@pytest.fixture
def auth_client(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    monkeypatch.setenv("CLERK_JWT_KEY", public_key)
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)
    monkeypatch.setenv("CLERK_ISSUER", "https://clerk.example.test")
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "https://vineyard.example.test")
    monkeypatch.delenv("CLERK_ALLOWED_USER_IDS", raising=False)
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        yield client, key
    app.dependency_overrides.clear()


def bearer(key, *, sub="user_family", expiry=60, issuer="https://clerk.example.test", party="https://vineyard.example.test"):
    now = int(time.time())
    token = jwt.encode({"sub": sub, "iss": issuer, "azp": party, "iat": now - 60, "nbf": now - 60, "exp": now + expiry}, key, algorithm="RS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("path,method", [
    ("/api/gardens", "get"),
    ("/api/reports/overview", "get"),
    ("/api/assistant/chat", "post"),
    ("/api/assistant/query", "post"),
    ("/api/assistant/actions/preview", "post"),
    ("/api/gardens", "post"),
    ("/db-health", "get"),
])
def test_business_routes_require_auth(auth_client, path, method):
    client, _ = auth_client
    assert getattr(client, method)(path).status_code == 401


def test_every_business_route_has_auth_dependency():
    business_routers = [route for route in app.routes if hasattr(route, "include_context")]
    assert len(business_routers) == 14
    assert all(
        any(dependency.dependency is get_current_user for dependency in route.include_context.dependencies)
        for route in business_routers
    )


def test_health_is_public(auth_client):
    client, _ = auth_client
    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_malformed_invalid_expired_and_wrong_claims(auth_client):
    client, key = auth_client
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for headers in (
        {"Authorization": "Bearer"},
        {"Authorization": "Basic nonsense"},
        {"Authorization": "Bearer nonsense"},
        bearer(other_key),
        bearer(key, expiry=-60),
        bearer(key, issuer="https://other.example.test"),
        bearer(key, party="https://other.example.test"),
    ):
        assert client.get("/api/gardens", headers=headers).status_code == 401


def test_valid_token_allows_protected_route_and_allowlist_rejects_other_user(auth_client, monkeypatch):
    client, key = auth_client
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def isolated_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = isolated_db
    assert client.get("/api/gardens", headers=bearer(key)).json() == []
    assert client.get("/api/reports/overview", headers=bearer(key)).status_code == 200
    assert client.post("/api/assistant/chat", headers=bearer(key), json={}).status_code == 422
    assert client.post("/api/gardens", headers=bearer(key), json={}).status_code == 422
    monkeypatch.setenv("CLERK_ALLOWED_USER_IDS", "user_other")
    assert client.post("/api/gardens", headers=bearer(key), json={}).status_code == 403
    app.dependency_overrides.pop(get_db)
    engine.dispose()


def test_direct_execution_not_exposed(auth_client):
    client, key = auth_client
    assert client.post("/api/assistant/actions/execute", headers=bearer(key), json={"confirmed": True}).status_code == 404


def test_db_health_hides_internal_error(auth_client, monkeypatch):
    client, key = auth_client

    def fail():
        raise RuntimeError("secret database host and password")

    monkeypatch.setattr("app.main.engine.connect", fail)
    response = client.get("/db-health", headers=bearer(key))
    assert response.status_code == 503
    assert "secret" not in response.text
    assert "password" not in response.text
