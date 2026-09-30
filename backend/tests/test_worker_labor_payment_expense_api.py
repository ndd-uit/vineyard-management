import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.models import (
    Expense,
    Garden,
    GrapeVariety,
    LaborRecord,
    Season,
    Worker,
    WorkerPayment,
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
            Worker.__table__,
            LaborRecord.__table__,
            WorkerPayment.__table__,
            Expense.__table__,
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


def create_worker(client: TestClient) -> int:
    response = client.post("/api/workers", json={"worker_name": "Anh Bình"})
    assert response.status_code == 201
    return response.json()["worker_id"]


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


def labor_payload(worker_id: int, season_id: int):
    return {
        "worker_id": worker_id,
        "season_id": season_id,
        "work_date": "2026-09-01",
        "work_type": "Cắt nho",
        "amount": "250000.00",
    }


def payment_payload(worker_id: int):
    return {
        "worker_id": worker_id,
        "payment_date": "2026-09-02",
        "amount": "300000.00",
    }


def expense_payload(season_id: int):
    return {
        "season_id": season_id,
        "expense_date": "2026-09-01",
        "category": "Phân bón",
        "amount": "120000.00",
        "description": "Phân hữu cơ",
    }


def test_create_worker(client: TestClient):
    worker_id = create_worker(client)
    response = client.get(f"/api/workers/{worker_id}")
    assert response.status_code == 200
    assert response.json()["worker_name"] == "Anh Bình"
    assert response.json()["created_at"]


def test_reject_blank_worker_name(client: TestClient):
    assert client.post(
        "/api/workers", json={"worker_name": "   "}
    ).status_code == 422


def test_create_labor_record_without_recording_payment(client: TestClient):
    response = client.post(
        "/api/labor-records",
        json=labor_payload(create_worker(client), create_season(client)),
    )
    assert response.status_code == 201
    assert response.json()["work_type"] == "Cắt nho"
    assert response.json()["amount"] == "250000.00"
    assert client.get("/api/worker-payments").json() == []


@pytest.mark.parametrize("invalid_field", ["worker_id", "season_id"])
def test_reject_invalid_labor_reference(client: TestClient, invalid_field: str):
    payload = labor_payload(create_worker(client), create_season(client))
    payload[invalid_field] = 9999
    assert client.post("/api/labor-records", json=payload).status_code == 422


def test_reject_blank_work_type(client: TestClient):
    payload = labor_payload(create_worker(client), create_season(client))
    payload["work_type"] = "   "
    assert client.post("/api/labor-records", json=payload).status_code == 422


@pytest.mark.parametrize("amount", ["0", "-1"])
def test_reject_nonpositive_labor_amount(client: TestClient, amount: str):
    payload = labor_payload(create_worker(client), create_season(client))
    payload["amount"] = amount
    assert client.post("/api/labor-records", json=payload).status_code == 422


def test_create_worker_payment_without_labor_link_or_balance_limit(
    client: TestClient,
):
    payload = payment_payload(create_worker(client))
    payload["labor_id"] = 9999
    response = client.post("/api/worker-payments", json=payload)
    assert response.status_code == 201
    assert response.json()["amount"] == "300000.00"
    assert "labor_id" not in response.json()


def test_reject_payment_with_invalid_worker(client: TestClient):
    assert client.post(
        "/api/worker-payments", json=payment_payload(9999)
    ).status_code == 422


@pytest.mark.parametrize("amount", ["0", "-1"])
def test_reject_nonpositive_payment(client: TestClient, amount: str):
    payload = payment_payload(create_worker(client))
    payload["amount"] = amount
    assert client.post("/api/worker-payments", json=payload).status_code == 422


def test_create_expense(client: TestClient):
    response = client.post(
        "/api/expenses", json=expense_payload(create_season(client))
    )
    assert response.status_code == 201
    assert response.json()["category"] == "Phân bón"
    assert response.json()["description"] == "Phân hữu cơ"


def test_reject_expense_with_invalid_season(client: TestClient):
    assert client.post(
        "/api/expenses", json=expense_payload(9999)
    ).status_code == 422


def test_reject_blank_expense_category(client: TestClient):
    payload = expense_payload(create_season(client))
    payload["category"] = "   "
    assert client.post("/api/expenses", json=payload).status_code == 422


@pytest.mark.parametrize("amount", ["0", "-1"])
def test_reject_nonpositive_expense_amount(client: TestClient, amount: str):
    payload = expense_payload(create_season(client))
    payload["amount"] = amount
    assert client.post("/api/expenses", json=payload).status_code == 422


@pytest.mark.parametrize(
    "category",
    ["Nhân công", " nhan cong ", "  NHÂN CÔNG  ", " LaBoR ", "Chi phí nhân công"],
)
def test_reject_labor_expense_category(client: TestClient, category: str):
    payload = expense_payload(create_season(client))
    payload["category"] = category
    assert client.post("/api/expenses", json=payload).status_code == 422


def test_patch_cannot_change_expense_to_labor_category(client: TestClient):
    expense = client.post(
        "/api/expenses", json=expense_payload(create_season(client))
    ).json()
    expense_url = f"/api/expenses/{expense['expense_id']}"
    response = client.patch(expense_url, json={"category": " labor "})
    assert response.status_code == 422
    assert client.get(expense_url).json()["category"] == "Phân bón"


def test_update_list_and_delete_new_resources(client: TestClient):
    worker_id = create_worker(client)
    season_id = create_season(client)
    labor = client.post(
        "/api/labor-records", json=labor_payload(worker_id, season_id)
    ).json()
    payment = client.post(
        "/api/worker-payments", json=payment_payload(worker_id)
    ).json()
    expense = client.post(
        "/api/expenses", json=expense_payload(season_id)
    ).json()
    assert len(client.get("/api/workers").json()) == 1
    assert len(client.get("/api/labor-records").json()) == 1
    assert len(client.get("/api/worker-payments").json()) == 1
    assert len(client.get("/api/expenses").json()) == 1

    assert client.patch(
        f"/api/workers/{worker_id}", json={"phone": "0123456789"}
    ).json()["phone"] == "0123456789"
    assert client.patch(
        f"/api/labor-records/{labor['labor_id']}", json={"work_type": "Làm cỏ"}
    ).json()["work_type"] == "Làm cỏ"
    assert client.patch(
        f"/api/worker-payments/{payment['worker_payment_id']}",
        json={"amount": "200000.00"},
    ).json()["amount"] == "200000.00"
    assert client.patch(
        f"/api/expenses/{expense['expense_id']}", json={"description": "Đợt 2"}
    ).json()["description"] == "Đợt 2"

    for path in (
        f"/api/labor-records/{labor['labor_id']}",
        f"/api/worker-payments/{payment['worker_payment_id']}",
        f"/api/expenses/{expense['expense_id']}",
        f"/api/workers/{worker_id}",
    ):
        assert client.delete(path).status_code == 204
        assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    ("collection", "detail"),
    [
        ("workers", "worker_id"),
        ("labor-records", "labor_id"),
        ("worker-payments", "worker_payment_id"),
        ("expenses", "expense_id"),
    ],
)
def test_final_crud_routes_are_registered(
    client: TestClient, collection: str, detail: str
):
    paths = app.openapi()["paths"]
    assert set(paths[f"/api/{collection}"]) == {"get", "post"}
    assert set(paths[f"/api/{collection}/{{{detail}}}"]) == {
        "get", "patch", "delete"
    }
