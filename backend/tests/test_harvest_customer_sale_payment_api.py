import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.models import (
    Customer,
    CustomerPayment,
    Garden,
    GrapeVariety,
    Harvest,
    Sale,
    Season,
)


@pytest.fixture
def client():
    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        test_engine,
        tables=[
            Garden.__table__,
            GrapeVariety.__table__,
            Season.__table__,
            Harvest.__table__,
            Customer.__table__,
            Sale.__table__,
            CustomerPayment.__table__,
        ],
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


def create_season(client: TestClient) -> int:
    garden = client.post("/api/gardens", json={"garden_name": "Vườn A"})
    variety = client.post(
        "/api/grape-varieties", json={"variety_name": "Nho đỏ"}
    )
    response = client.post(
        "/api/seasons",
        json={
            "garden_id": garden.json()["garden_id"],
            "variety_id": variety.json()["variety_id"],
            "acquisition_type": "OWNED",
            "status": "ACTIVE",
        },
    )
    assert response.status_code == 201
    return response.json()["season_id"]


def create_harvest(client: TestClient, quantity_kg: str = "10.00") -> int:
    response = client.post(
        "/api/harvests",
        json={
            "season_id": create_season(client),
            "harvest_date": "2026-09-01",
            "quantity_kg": quantity_kg,
        },
    )
    assert response.status_code == 201
    return response.json()["harvest_id"]


def create_customer(client: TestClient) -> int:
    response = client.post("/api/customers", json={"customer_name": "Đại lý A"})
    assert response.status_code == 201
    return response.json()["customer_id"]


def sale_payload(harvest_id: int, customer_id: int, quantity: str = "2.00"):
    return {
        "harvest_id": harvest_id,
        "customer_id": customer_id,
        "sale_date": "2026-09-02",
        "quantity_kg": quantity,
        "unit_price": "12.34",
    }


def test_create_harvest_with_valid_season(client: TestClient):
    harvest_id = create_harvest(client)
    response = client.get(f"/api/harvests/{harvest_id}")
    assert response.status_code == 200
    assert response.json()["quantity_kg"] == "10.00"


def test_reject_harvest_with_invalid_season(client: TestClient):
    response = client.post(
        "/api/harvests",
        json={"season_id": 9999, "harvest_date": "2026-09-01", "quantity_kg": "1.00"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("quantity", ["0", "-1"])
def test_reject_nonpositive_harvest_quantity(client: TestClient, quantity: str):
    response = client.post(
        "/api/harvests",
        json={
            "season_id": create_season(client),
            "harvest_date": "2026-09-01",
            "quantity_kg": quantity,
        },
    )
    assert response.status_code == 422


def test_create_customer_and_reject_blank_name(client: TestClient):
    customer_id = create_customer(client)
    assert client.get(f"/api/customers/{customer_id}").status_code == 200
    assert client.post(
        "/api/customers", json={"customer_name": "   "}
    ).status_code == 422


def test_create_sale_calculates_total_and_ignores_client_total(client: TestClient):
    harvest_id = create_harvest(client)
    customer_id = create_customer(client)
    payload = sale_payload(harvest_id, customer_id, quantity="1.25")
    payload["total_amount"] = "999999.99"
    response = client.post("/api/sales", json=payload)
    assert response.status_code == 201
    assert response.json()["total_amount"] == "15.43"
    assert response.json()["quantity_kg"] == "1.25"


@pytest.mark.parametrize("invalid_field", ["harvest_id", "customer_id"])
def test_reject_invalid_sale_foreign_key(client: TestClient, invalid_field: str):
    payload = sale_payload(create_harvest(client), create_customer(client))
    payload[invalid_field] = 9999
    assert client.post("/api/sales", json=payload).status_code == 422


def test_reject_sale_exceeding_harvest(client: TestClient):
    payload = sale_payload(create_harvest(client), create_customer(client), "10.01")
    assert client.post("/api/sales", json=payload).status_code == 422


def test_multiple_sales_consume_harvest_quantity(client: TestClient):
    harvest_id = create_harvest(client)
    customer_id = create_customer(client)
    assert client.post(
        "/api/sales", json=sale_payload(harvest_id, customer_id, "6.00")
    ).status_code == 201
    assert client.post(
        "/api/sales", json=sale_payload(harvest_id, customer_id, "4.00")
    ).status_code == 201
    assert client.post(
        "/api/sales", json=sale_payload(harvest_id, customer_id, "0.01")
    ).status_code == 422


def test_patch_sale_recalculates_total(client: TestClient):
    harvest_id = create_harvest(client)
    customer_id = create_customer(client)
    sale = client.post(
        "/api/sales", json=sale_payload(harvest_id, customer_id)
    ).json()
    response = client.patch(
        f"/api/sales/{sale['sale_id']}",
        json={"quantity_kg": "3.00", "unit_price": "5.00", "total_amount": "1.00"},
    )
    assert response.status_code == 200
    assert response.json()["total_amount"] == "15.00"


def test_patch_sale_availability_excludes_current_sale(client: TestClient):
    harvest_id = create_harvest(client)
    customer_id = create_customer(client)
    sale = client.post(
        "/api/sales", json=sale_payload(harvest_id, customer_id, "6.00")
    ).json()
    sale_url = f"/api/sales/{sale['sale_id']}"
    assert client.patch(sale_url, json={"quantity_kg": "8.00"}).status_code == 200
    assert client.patch(sale_url, json={"quantity_kg": "10.01"}).status_code == 422
    assert client.get(sale_url).json()["quantity_kg"] == "8.00"


def test_harvest_cannot_shrink_below_quantity_sold(client: TestClient):
    harvest_id = create_harvest(client)
    customer_id = create_customer(client)
    client.post("/api/sales", json=sale_payload(harvest_id, customer_id, "6.00"))
    response = client.patch(
        f"/api/harvests/{harvest_id}", json={"quantity_kg": "5.00"}
    )
    assert response.status_code == 422


def test_create_customer_payment_without_sale_link(client: TestClient):
    response = client.post(
        "/api/customer-payments",
        json={
            "customer_id": create_customer(client),
            "payment_date": "2026-09-03",
            "amount": "100.00",
            "sale_id": 9999,
        },
    )
    assert response.status_code == 201
    assert response.json()["amount"] == "100.00"
    assert "sale_id" not in response.json()


def test_reject_payment_with_invalid_customer(client: TestClient):
    response = client.post(
        "/api/customer-payments",
        json={"customer_id": 9999, "payment_date": "2026-09-03", "amount": "1.00"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("amount", ["0", "-1"])
def test_reject_nonpositive_payment(client: TestClient, amount: str):
    response = client.post(
        "/api/customer-payments",
        json={
            "customer_id": create_customer(client),
            "payment_date": "2026-09-03",
            "amount": amount,
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("collection", "detail"),
    [
        ("harvests", "harvest_id"),
        ("customers", "customer_id"),
        ("sales", "sale_id"),
        ("customer-payments", "payment_id"),
    ],
)
def test_new_crud_routes_are_registered(
    client: TestClient, collection: str, detail: str
):
    paths = app.openapi()["paths"]
    assert set(paths[f"/api/{collection}"]) == {"get", "post"}
    assert set(paths[f"/api/{collection}/{{{detail}}}"]) == {
        "get", "patch", "delete"
    }
