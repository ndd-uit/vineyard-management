from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.schemas.assistant_actions import WriteAction
from app.services import assistant_actions
from app.models import (
    Customer,
    CustomerPayment,
    Expense,
    Garden,
    GrapeVariety,
    Harvest,
    LaborRecord,
    Sale,
    Season,
    Worker,
    WorkerPayment,
)


@pytest.fixture
def client_and_engine(monkeypatch):
    monkeypatch.setenv("ASSISTANT_ACTION_SIGNING_KEY", "test-only-signing-key-at-least-32-bytes")
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(sub="test-user")
    try:
        with TestClient(app) as client:
            yield client, engine
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def seed(engine):
    with Session(engine) as db:
        garden = Garden(garden_name="Vườn A")
        variety = GrapeVariety(variety_name="Nho A")
        customer = Customer(customer_name="Cô Lan")
        worker = Worker(worker_name="Anh Tâm")
        db.add_all([garden, variety, customer, worker])
        db.flush()
        season = Season(
            garden_id=garden.garden_id,
            variety_id=variety.variety_id,
            season_name="Mùa 2026",
            acquisition_type="OWNED",
            status="ACTIVE",
        )
        db.add(season)
        db.flush()
        harvest = Harvest(
            season_id=season.season_id,
            harvest_date=date(2026, 9, 1),
            quantity_kg=Decimal("10.00"),
        )
        db.add(harvest)
        db.flush()
        ids = {
            "garden_id": garden.garden_id,
            "season_id": season.season_id,
            "harvest_id": harvest.harvest_id,
            "customer_id": customer.customer_id,
            "worker_id": worker.worker_id,
        }
        db.commit()
        return ids


def count(engine, model):
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(model))


def action(action_name, **arguments):
    return {"action": action_name, "arguments": arguments}


def execute_internal(engine, payload):
    """Exercise the service without exposing its unsafe legacy HTTP endpoint."""
    validated = TypeAdapter(WriteAction).validate_python(payload)
    with Session(engine) as db:
        return assistant_actions.execute(db, validated)


def test_find_grape_varieties_exact_partial_and_missing(client_and_engine):
    client, engine = client_and_engine
    with Session(engine) as db:
        db.add_all([
            GrapeVariety(variety_name="Hồng Nhật", note="Giống đỏ"),
            GrapeVariety(variety_name="Hồng Mẫu Đơn"),
        ])
        db.commit()
    exact = client.post("/api/assistant/query", json=action("find_grape_varieties", name="hồng nhật"))
    assert exact.status_code == 200
    assert len(exact.json()["result"]) == 1
    assert exact.json()["result"][0]["variety_name"] == "Hồng Nhật"
    assert exact.json()["result"][0]["note"] == "Giống đỏ"
    assert exact.json()["result"][0]["variety_id"] > 0
    partial = client.post("/api/assistant/query", json=action("find_grape_varieties", name="HỒNG"))
    assert partial.status_code == 200
    assert len(partial.json()["result"]) == 2
    missing = client.post("/api/assistant/query", json=action("find_grape_varieties", name="Mẫu lạ"))
    assert missing.status_code == 200
    assert missing.json()["result"] == []


def test_grape_variety_action_blocks_likely_duplicate_before_preview(client_and_engine):
    client, engine = client_and_engine
    with Session(engine) as db:
        db.add(GrapeVariety(variety_name="Hồng Nhật"))
        db.commit()
    response = client.post("/api/assistant/actions/preview", json=action("create_grape_variety", variety_name="Hong Nhat"))
    assert response.status_code == 422
    assert count(engine, GrapeVariety) == 1


def test_create_season_action_previews_confirms_and_revalidates(client_and_engine):
    client, engine = client_and_engine
    seed(engine)
    with Session(engine) as db:
        garden_id = db.scalar(select(Garden.garden_id))
        variety_id = db.scalar(select(GrapeVariety.variety_id))
    arguments = dict(
        garden_id=garden_id, variety_id=variety_id, season_name="Vụ mới",
        start_date="2026-09-01", end_date="2026-12-01",
        acquisition_type="OWNED", status="PLANNING",
    )
    preview = client.post("/api/assistant/actions/preview", json=action("create_season", **arguments))
    assert preview.status_code == 200
    assert preview.json()["action"] == "create_season"
    assert preview.json()["action_token"].startswith("v1.")
    assert count(engine, Season) == 1
    unconfirmed = client.post("/api/assistant/actions/execute", json=action("create_season", **arguments))
    assert unconfirmed.status_code == 404
    confirmed = execute_internal(engine, {**action("create_season", **arguments), "confirmed": True})
    assert confirmed.resource_type == "seasons"
    assert count(engine, Season) == 2


@pytest.mark.parametrize("bad_field, bad_value", [
    ("garden_id", 99999),
    ("variety_id", 99999),
    ("purchase_price", "100.00"),
    ("end_date", "2026-08-31"),
])
def test_create_season_action_rejects_invalid_business_rules(client_and_engine, bad_field, bad_value):
    client, engine = client_and_engine
    seed(engine)
    with Session(engine) as db:
        garden_id = db.scalar(select(Garden.garden_id))
        variety_id = db.scalar(select(GrapeVariety.variety_id))
    arguments = dict(
        garden_id=garden_id, variety_id=variety_id,
        start_date="2026-09-01", end_date="2026-12-01",
        acquisition_type="OWNED", status="PLANNING",
    )
    arguments[bad_field] = bad_value
    response = client.post("/api/assistant/actions/preview", json=action("create_season", **arguments))
    assert response.status_code == 422
    assert count(engine, Season) == 1


@pytest.mark.parametrize("acquisition, status_name, price, expected", [
    ("OWNED", "ACTIVE", None, "Đây là vườn nhà mình."),
    ("PURCHASED", "PLANNING", "20000000.00", "mua quyền thu hoạch với giá 20.000.000đ"),
    ("OWNED", "PLANNING", None, "đang chuẩn bị"),
    ("OWNED", "HARVESTING", None, "đang thu hoạch"),
    ("OWNED", "COMPLETED", None, "đã kết thúc"),
])
def test_season_preview_uses_natural_vietnamese(client_and_engine, acquisition, status_name, price, expected):
    client, engine = client_and_engine
    seed(engine)
    with Session(engine) as db:
        garden_id = db.scalar(select(Garden.garden_id))
        variety_id = db.scalar(select(GrapeVariety.variety_id))
    args = dict(garden_id=garden_id, variety_id=variety_id, season_name="Vụ tháng 9",
                acquisition_type=acquisition, status=status_name)
    if price is not None:
        args["purchase_price"] = price
    response = client.post("/api/assistant/actions/preview", json=action("create_season", **args))
    assert response.status_code == 200
    body = response.json()
    summary = body["summary"]
    assert "vụ tháng 9" in summary
    assert "vườn A" in summary
    assert "Nho A" in summary
    assert expected in summary
    assert all(term not in summary for term in ("OWNED", "PURCHASED", "ACTIVE", "PLANNING", "HARVESTING", "COMPLETED", "create_season", "garden_id", "variety_id"))
    assert body["arguments"]["acquisition_type"] == acquisition
    assert body["arguments"]["status"] == status_name
    assert count(engine, Season) == 1


@pytest.mark.parametrize("name, args, expected", [
    ("record_harvest", {"season_id": "season_id", "harvest_date": "2026-09-02", "quantity_kg": "120.00"}, ("vườn A", "120 kg")),
    ("record_sale", {"harvest_id": "harvest_id", "customer_id": "customer_id", "sale_date": "2026-09-02", "quantity_kg": "2.00", "unit_price": "80000.00"}, ("cô Lan", "2 kg", "80.000đ/kg", "160.000đ")),
    ("record_customer_payment", {"customer_id": "customer_id", "payment_date": "2026-09-02", "amount": "1000000.00"}, ("Cô Lan", "1.000.000đ")),
    ("record_labor", {"worker_id": "worker_id", "season_id": "season_id", "work_date": "2026-09-02", "work_type": "Cắt nho", "amount": "500000.00"}, ("Anh Tâm", "cắt nho", "500.000đ")),
    ("record_worker_payment", {"worker_id": "worker_id", "payment_date": "2026-09-02", "amount": "300000.00"}, ("anh Tâm", "300.000đ")),
    ("record_expense", {"season_id": "season_id", "expense_date": "2026-09-02", "category": "Phân bón", "amount": "700000.00"}, ("700.000đ", "phân bón", "mùa 2026")),
])
def test_write_summaries_show_names_and_formatted_values(client_and_engine, name, args, expected):
    client, engine = client_and_engine
    ids = seed(engine)
    values = {key: ids.get(value, value) for key, value in args.items()}
    response = client.post("/api/assistant/actions/preview", json=action(name, **values))
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert all(piece in summary for piece in expected)
    assert all(term not in summary for term in (name, "season_id", "customer_id", "worker_id", "harvest_id"))


def test_previews_validate_and_never_write(client_and_engine):
    client, engine = client_and_engine
    ids = seed(engine)
    cases = [
        (
            "record_harvest",
            {"season_id": ids["season_id"], "harvest_date": "2026-09-02", "quantity_kg": "5.00"},
            Harvest,
        ),
        (
            "record_sale",
            {"harvest_id": ids["harvest_id"], "customer_id": ids["customer_id"], "sale_date": "2026-09-02", "quantity_kg": "2.00", "unit_price": "7.25"},
            Sale,
        ),
        (
            "record_expense",
            {"season_id": ids["season_id"], "expense_date": "2026-09-02", "category": "Phân bón", "amount": "50.00"},
            Expense,
        ),
    ]
    for name, arguments, model in cases:
        before = count(engine, model)
        response = client.post("/api/assistant/actions/preview", json=action(name, **arguments))
        assert response.status_code == 200
        assert response.json()["requires_confirmation"] is True
        assert response.json()["summary"]
        assert count(engine, model) == before
    assert response.json()["calculated"] == {}

    sale_preview = client.post(
        "/api/assistant/actions/preview",
        json=action("record_sale", harvest_id=ids["harvest_id"], customer_id=ids["customer_id"], sale_date="2026-09-02", quantity_kg="2.00", unit_price="7.25"),
    ).json()
    assert sale_preview["calculated"]["total_amount"] == "14.50"
    assert "14,5đ" in sale_preview["summary"]
    assert "total_amount" not in sale_preview["arguments"]
    assert count(engine, Sale) == 0


def test_invalid_previews_and_confirmation_never_write(client_and_engine):
    client, engine = client_and_engine
    ids = seed(engine)
    bad = client.post(
        "/api/assistant/actions/preview",
        json=action("record_harvest", season_id=999, harvest_date="2026-09-02", quantity_kg="1.00"),
    )
    assert bad.status_code == 422
    assert count(engine, Harvest) == 1
    payload = action("record_harvest", season_id=ids["season_id"], harvest_date="2026-09-02", quantity_kg="1.00")
    assert client.post("/api/assistant/actions/execute", json=payload).status_code == 404
    with pytest.raises(HTTPException):
        execute_internal(engine, payload)
    with pytest.raises(HTTPException):
        execute_internal(engine, {**payload, "confirmed": False})
    with pytest.raises(ValidationError):
        execute_internal(engine, {**payload, "confirmed": "true"})
    assert count(engine, Harvest) == 1


@pytest.mark.parametrize(
    ("name", "arguments", "model"),
    [
        ("record_harvest", {"season_id": "season_id", "harvest_date": "2026-09-02", "quantity_kg": "5.00"}, Harvest),
        ("record_sale", {"harvest_id": "harvest_id", "customer_id": "customer_id", "sale_date": "2026-09-02", "quantity_kg": "2.00", "unit_price": "7.25"}, Sale),
        ("record_customer_payment", {"customer_id": "customer_id", "payment_date": "2026-09-02", "amount": "10.00"}, CustomerPayment),
        ("record_labor", {"worker_id": "worker_id", "season_id": "season_id", "work_date": "2026-09-02", "work_type": "Cắt nho", "amount": "20.00"}, LaborRecord),
        ("record_worker_payment", {"worker_id": "worker_id", "payment_date": "2026-09-02", "amount": "8.00"}, WorkerPayment),
        ("record_expense", {"season_id": "season_id", "expense_date": "2026-09-02", "category": "Phân bón", "amount": "5.00"}, Expense),
        ("create_customer", {"customer_name": "Khách mới"}, Customer),
        ("create_worker", {"worker_name": "Thợ mới"}, Worker),
        ("create_garden", {"garden_name": "Vườn mới"}, Garden),
    ],
)
def test_confirmed_action_creates_exactly_one_record(client_and_engine, name, arguments, model):
    client, engine = client_and_engine
    ids = seed(engine)
    values = {key: ids.get(value, value) for key, value in arguments.items()}
    before = count(engine, model)
    response = execute_internal(engine, {**action(name, **values), "confirmed": True})
    assert response.resource_id > 0
    assert response.message == "Con đã ghi lại rồi ạ."
    assert count(engine, model) == before + 1
    if name == "record_sale":
        with Session(engine) as db:
            sale = db.get(Sale, response.resource_id)
            assert sale.total_amount == Decimal("14.50")
        assert response.result["total_amount"] == "14.50"


def test_execute_revalidates_changed_harvest_availability(client_and_engine):
    client, engine = client_and_engine
    ids = seed(engine)
    payload = action("record_sale", harvest_id=ids["harvest_id"], customer_id=ids["customer_id"], sale_date="2026-09-03", quantity_kg="6.00", unit_price="3.00")
    assert client.post("/api/assistant/actions/preview", json=payload).status_code == 200
    with Session(engine) as db:
        db.add(Sale(harvest_id=ids["harvest_id"], customer_id=ids["customer_id"], sale_date=date(2026, 9, 2), quantity_kg=Decimal("6.00"), unit_price=Decimal("2.00"), total_amount=Decimal("12.00")))
        db.commit()
    with pytest.raises(HTTPException) as error:
        execute_internal(engine, {**payload, "confirmed": True})
    assert error.value.status_code == 422
    assert count(engine, Sale) == 1


def test_sale_capacity_and_labor_expense_rules(client_and_engine):
    client, engine = client_and_engine
    ids = seed(engine)
    oversized = action("record_sale", harvest_id=ids["harvest_id"], customer_id=ids["customer_id"], sale_date="2026-09-02", quantity_kg="11.00", unit_price="1.00")
    assert client.post("/api/assistant/actions/preview", json=oversized).status_code == 422
    with pytest.raises(HTTPException):
        execute_internal(engine, {**oversized, "confirmed": True})
    labor_expense = action("record_expense", season_id=ids["season_id"], expense_date="2026-09-02", category="Tiền công", amount="10.00")
    assert client.post("/api/assistant/actions/preview", json=labor_expense).status_code == 422
    with pytest.raises(HTTPException):
        execute_internal(engine, {**labor_expense, "confirmed": True})
    assert count(engine, Sale) == 0
    assert count(engine, Expense) == 0


def test_lookup_returns_all_ambiguous_matches_and_no_match(client_and_engine):
    client, engine = client_and_engine
    seed(engine)
    with Session(engine) as db:
        db.add_all([Customer(customer_name="Chị Lan"), Worker(worker_name="Chị Tâm")])
        db.commit()
    customers = client.post("/api/assistant/query", json=action("find_customers", name="lan"))
    assert customers.status_code == 200
    assert len(customers.json()["result"]) == 2
    workers = client.post("/api/assistant/query", json=action("find_workers", name="Tâm"))
    assert len(workers.json()["result"]) == 2
    assert client.post("/api/assistant/query", json=action("find_customers", name="Không có")).json()["result"] == []
    assert len(client.post("/api/assistant/query", json=action("find_gardens", name="Vườn")).json()["result"]) == 1
    assert len(client.post("/api/assistant/query", json=action("find_seasons", name="2026")).json()["result"]) == 1


def test_query_reuses_reports(client_and_engine):
    client, engine = client_and_engine
    ids = seed(engine)
    cases = [
        ("get_customer_receivable", {"customer_id": ids["customer_id"]}, f"/api/reports/customer-receivables/{ids['customer_id']}"),
        ("get_worker_payable", {"worker_id": ids["worker_id"]}, f"/api/reports/worker-payables/{ids['worker_id']}"),
        ("get_season_summary", {"season_id": ids["season_id"]}, f"/api/reports/seasons/{ids['season_id']}/summary"),
        ("get_business_overview", {}, "/api/reports/overview"),
    ]
    for name, arguments, report_path in cases:
        response = client.post("/api/assistant/query", json=action(name, **arguments))
        assert response.status_code == 200
        assert response.json()["result"] == client.get(report_path).json()
    assert client.post("/api/assistant/query", json=action("get_customer_receivable", customer_id=999)).status_code == 404


def test_unknown_action_and_arbitrary_function_are_rejected(client_and_engine):
    client, engine = client_and_engine
    for endpoint in ("/api/assistant/actions/preview", "/api/assistant/query"):
        payload = action("__import__", command="drop everything")
        if endpoint.endswith("execute"):
            payload["confirmed"] = True
        assert client.post(endpoint, json=payload).status_code == 422
    assert count(engine, Garden) == 0
    assert client.post("/api/assistant/actions/execute", json={"confirmed": True}).status_code == 404


def test_unknown_argument_cannot_override_backend_calculated_total(client_and_engine):
    client, engine = client_and_engine
    ids = seed(engine)
    payload = action(
        "record_sale",
        harvest_id=ids["harvest_id"],
        customer_id=ids["customer_id"],
        sale_date="2026-09-02",
        quantity_kg="2.00",
        unit_price="7.25",
        total_amount="0.01",
    )
    assert client.post("/api/assistant/actions/preview", json=payload).status_code == 422
    with pytest.raises(ValidationError):
        execute_internal(engine, {**payload, "confirmed": True})
    assert count(engine, Sale) == 0
