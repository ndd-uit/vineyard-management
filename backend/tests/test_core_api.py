import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.models import Garden, GrapeVariety, Season


@pytest.fixture
def client():
    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        test_engine,
        tables=[Garden.__table__, GrapeVariety.__table__, Season.__table__],
    )

    def override_get_db():
        with Session(test_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(sub="test-user")
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        test_engine.dispose()


def create_references(client: TestClient) -> tuple[int, int]:
    garden = client.post("/api/gardens", json={"garden_name": "Vườn A"})
    variety = client.post(
        "/api/grape-varieties", json={"variety_name": "Nho đỏ"}
    )
    assert garden.status_code == 201
    assert variety.status_code == 201
    return garden.json()["garden_id"], variety.json()["variety_id"]


def test_create_garden(client: TestClient):
    response = client.post(
        "/api/gardens",
        json={"garden_name": "Vườn A", "owner_name": "Gia đình A"},
    )
    assert response.status_code == 201
    assert response.json()["garden_name"] == "Vườn A"
    assert response.json()["created_at"]


def test_list_gardens(client: TestClient):
    client.post("/api/gardens", json={"garden_name": "Vườn A"})
    response = client.get("/api/gardens")
    assert response.status_code == 200
    assert [item["garden_name"] for item in response.json()] == ["Vườn A"]


def test_create_grape_variety(client: TestClient):
    response = client.post(
        "/api/grape-varieties", json={"variety_name": "Nho đỏ"}
    )
    assert response.status_code == 201
    assert response.json()["variety_name"] == "Nho đỏ"


def test_create_season_with_valid_foreign_keys(client: TestClient):
    garden_id, variety_id = create_references(client)
    response = client.post(
        "/api/seasons",
        json={
            "garden_id": garden_id,
            "variety_id": variety_id,
            "acquisition_type": "PURCHASED",
            "purchase_price": "125000.00",
            "status": "PLANNING",
            "start_date": "2026-01-01",
            "end_date": "2026-03-01",
        },
    )
    assert response.status_code == 201
    assert response.json()["purchase_price"] == "125000.00"
    assert response.json()["garden_id"] == garden_id


@pytest.mark.parametrize("invalid_field", ["garden_id", "variety_id"])
def test_reject_invalid_season_foreign_key(
    client: TestClient, invalid_field: str
):
    garden_id, variety_id = create_references(client)
    payload = {
        "garden_id": garden_id,
        "variety_id": variety_id,
        "acquisition_type": "OWNED",
        "status": "ACTIVE",
    }
    payload[invalid_field] = 9999
    response = client.post("/api/seasons", json=payload)
    assert response.status_code == 422


def test_reject_invalid_date_range(client: TestClient):
    garden_id, variety_id = create_references(client)
    response = client.post(
        "/api/seasons",
        json={
            "garden_id": garden_id,
            "variety_id": variety_id,
            "acquisition_type": "OWNED",
            "status": "ACTIVE",
            "start_date": "2026-04-01",
            "end_date": "2026-03-01",
        },
    )
    assert response.status_code == 422


def test_reject_purchase_price_for_owned_season(client: TestClient):
    garden_id, variety_id = create_references(client)
    response = client.post(
        "/api/seasons",
        json={
            "garden_id": garden_id,
            "variety_id": variety_id,
            "acquisition_type": "OWNED",
            "purchase_price": "100.00",
            "status": "ACTIVE",
        },
    )
    assert response.status_code == 422


def test_patch_validates_combined_season_dates(client: TestClient):
    garden_id, variety_id = create_references(client)
    season = client.post(
        "/api/seasons",
        json={
            "garden_id": garden_id,
            "variety_id": variety_id,
            "acquisition_type": "OWNED",
            "status": "ACTIVE",
            "start_date": "2026-04-01",
            "end_date": "2026-05-01",
        },
    )
    season_id = season.json()["season_id"]
    response = client.patch(
        f"/api/seasons/{season_id}", json={"end_date": "2026-03-01"}
    )
    assert response.status_code == 422
    assert client.get(f"/api/seasons/{season_id}").json()["end_date"] == "2026-05-01"


def test_read_update_delete_and_missing_record(client: TestClient):
    garden = client.post("/api/gardens", json={"garden_name": "Vườn A"}).json()
    garden_id = garden["garden_id"]
    assert client.get(f"/api/gardens/{garden_id}").status_code == 200
    updated = client.patch(
        f"/api/gardens/{garden_id}", json={"owner_name": "Gia đình B"}
    )
    assert updated.status_code == 200
    assert updated.json()["owner_name"] == "Gia đình B"
    assert client.delete(f"/api/gardens/{garden_id}").status_code == 204
    assert client.get(f"/api/gardens/{garden_id}").status_code == 404
