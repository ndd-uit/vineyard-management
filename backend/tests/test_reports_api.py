from datetime import date
from decimal import Decimal

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
def report_client():
    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    with Session(test_engine) as db:
        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(sub="test-user")
        try:
            with TestClient(app) as client:
                yield client, db
        finally:
            app.dependency_overrides.clear()
    test_engine.dispose()


def seed_core(db: Session, *, acquisition_type="PURCHASED", purchase_price="200.00"):
    garden = Garden(garden_name="Garden A")
    variety = GrapeVariety(variety_name="Grape A")
    db.add_all([garden, variety])
    db.flush()
    season = Season(
        garden_id=garden.garden_id,
        variety_id=variety.variety_id,
        season_name="Season A",
        acquisition_type=acquisition_type,
        purchase_price=Decimal(purchase_price) if purchase_price is not None else None,
        status="ACTIVE",
    )
    db.add(season)
    db.flush()
    return season


def seed_sales(db: Session, season: Season, customer: Customer):
    harvest = Harvest(
        season_id=season.season_id,
        harvest_date=date(2026, 9, 1),
        quantity_kg=Decimal("100.00"),
    )
    db.add(harvest)
    db.flush()
    db.add_all([
        Sale(
            harvest_id=harvest.harvest_id,
            customer_id=customer.customer_id,
            sale_date=date(2026, 9, 3),
            quantity_kg=Decimal("20.00"),
            unit_price=Decimal("10.00"),
            total_amount=Decimal("200.00"),
        ),
        Sale(
            harvest_id=harvest.harvest_id,
            customer_id=customer.customer_id,
            sale_date=date(2026, 9, 5),
            quantity_kg=Decimal("10.00"),
            unit_price=Decimal("10.00"),
            total_amount=Decimal("100.00"),
        ),
    ])


def test_empty_reports_are_zero_safe(report_client):
    client, _ = report_client
    assert client.get("/api/reports/customer-receivables").json() == []
    assert client.get("/api/reports/worker-payables").json() == []
    overview = client.get("/api/reports/overview")
    assert overview.status_code == 200
    assert all(Decimal(value) == 0 for value in overview.json().values())


def test_customer_receivables_aggregate_without_join_multiplication(report_client):
    client, db = report_client
    season = seed_core(db)
    customer = Customer(customer_name="Buyer A")
    inactive = Customer(customer_name="Buyer B")
    db.add_all([customer, inactive])
    db.flush()
    seed_sales(db, season, customer)
    db.add_all([
        CustomerPayment(customer_id=customer.customer_id, payment_date=date(2026, 9, 4), amount=Decimal("40.00")),
        CustomerPayment(customer_id=customer.customer_id, payment_date=date(2026, 9, 6), amount=Decimal("60.00")),
    ])
    db.commit()

    response = client.get("/api/reports/customer-receivables")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    assert rows[0]["total_sales"] == "300.00"
    assert rows[0]["total_payments"] == "100.00"
    assert rows[0]["outstanding_amount"] == "200.00"
    assert rows[1]["outstanding_amount"] == "0.00"

    detail = client.get(f"/api/reports/customer-receivables/{customer.customer_id}")
    assert detail.status_code == 200
    assert [(item["date"], item["type"]) for item in detail.json()["history"]] == [
        ("2026-09-03", "SALE"),
        ("2026-09-04", "PAYMENT"),
        ("2026-09-05", "SALE"),
        ("2026-09-06", "PAYMENT"),
    ]
    assert client.get(f"/api/reports/customer-receivables/{inactive.customer_id}").json()["history"] == []
    assert client.get("/api/reports/customer-receivables/999").status_code == 404


def test_worker_payables_and_chronological_history(report_client):
    client, db = report_client
    season = seed_core(db)
    worker = Worker(worker_name="Worker A")
    idle = Worker(worker_name="Worker B")
    db.add_all([worker, idle])
    db.flush()
    db.add_all([
        LaborRecord(worker_id=worker.worker_id, season_id=season.season_id, work_date=date(2026, 9, 3), work_type="Pruning", amount=Decimal("80.00")),
        LaborRecord(worker_id=worker.worker_id, season_id=season.season_id, work_date=date(2026, 9, 5), work_type="Harvesting", amount=Decimal("70.00")),
        WorkerPayment(worker_id=worker.worker_id, payment_date=date(2026, 9, 4), amount=Decimal("30.00")),
        WorkerPayment(worker_id=worker.worker_id, payment_date=date(2026, 9, 6), amount=Decimal("20.00")),
    ])
    db.commit()

    rows = client.get("/api/reports/worker-payables").json()
    assert len(rows) == 2
    assert rows[0]["total_labor"] == "150.00"
    assert rows[0]["total_payments"] == "50.00"
    assert rows[0]["outstanding_amount"] == "100.00"
    assert rows[1]["outstanding_amount"] == "0.00"

    detail = client.get(f"/api/reports/worker-payables/{worker.worker_id}")
    assert detail.status_code == 200
    history = detail.json()["history"]
    assert [item["type"] for item in history] == ["LABOR", "PAYMENT", "LABOR", "PAYMENT"]
    assert history[0]["work_type"] == "Pruning"
    assert history[0]["work_date"] == "2026-09-03"
    assert history[1]["payment_date"] == "2026-09-04"
    assert "work_type" not in history[1]
    assert client.get(f"/api/reports/worker-payables/{idle.worker_id}").json()["history"] == []
    assert client.get("/api/reports/worker-payables/999").status_code == 404


def test_season_summary_costs_and_remaining_quantity(report_client):
    client, db = report_client
    season = seed_core(db)
    customer = Customer(customer_name="Buyer A")
    worker = Worker(worker_name="Worker A")
    db.add_all([customer, worker])
    db.flush()
    seed_sales(db, season, customer)
    db.add_all([
        Expense(season_id=season.season_id, expense_date=date(2026, 9, 2), category="Fertilizer", amount=Decimal("30.00")),
        LaborRecord(worker_id=worker.worker_id, season_id=season.season_id, work_date=date(2026, 9, 2), work_type="Pruning", amount=Decimal("50.00")),
    ])
    db.commit()

    response = client.get(f"/api/reports/seasons/{season.season_id}/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["garden_name"] == "Garden A"
    assert data["variety_name"] == "Grape A"
    assert data["acquisition_type"] == "PURCHASED"
    assert data["total_harvest_kg"] == "100.00"
    assert data["total_sold_kg"] == "30.00"
    assert data["remaining_kg"] == "70.00"
    assert data["sales_revenue"] == "300.00"
    assert data["purchase_cost"] == "200.00"
    assert data["operating_expenses"] == "30.00"
    assert data["labor_cost"] == "50.00"
    assert data["total_cost"] == "280.00"
    assert data["estimated_profit"] == "20.00"
    assert client.get("/api/reports/seasons/999/summary").status_code == 404


def test_overview_uses_accrual_totals_not_cash_payments(report_client):
    client, db = report_client
    season = seed_core(db)
    owned = seed_core_second(db)
    customer = Customer(customer_name="Buyer A")
    worker = Worker(worker_name="Worker A")
    db.add_all([customer, worker])
    db.flush()
    seed_sales(db, season, customer)
    db.add_all([
        CustomerPayment(customer_id=customer.customer_id, payment_date=date(2026, 9, 7), amount=Decimal("100.00")),
        LaborRecord(worker_id=worker.worker_id, season_id=season.season_id, work_date=date(2026, 9, 2), work_type="Pruning", amount=Decimal("50.00")),
        WorkerPayment(worker_id=worker.worker_id, payment_date=date(2026, 9, 8), amount=Decimal("20.00")),
        Expense(season_id=season.season_id, expense_date=date(2026, 9, 2), category="Fertilizer", amount=Decimal("30.00")),
        Harvest(season_id=owned.season_id, harvest_date=date(2026, 9, 10), quantity_kg=Decimal("25.00")),
    ])
    db.commit()

    data = client.get("/api/reports/overview").json()
    assert data["total_harvest_kg"] == "125.00"
    assert data["total_sold_kg"] == "30.00"
    assert data["remaining_kg"] == "95.00"
    assert data["total_sales_revenue"] == "300.00"
    assert data["total_customer_payments"] == "100.00"
    assert data["total_customer_receivables"] == "200.00"
    assert data["total_labor_cost"] == "50.00"
    assert data["total_worker_payments"] == "20.00"
    assert data["total_worker_payables"] == "30.00"
    assert data["total_operating_expenses"] == "30.00"
    assert data["total_purchase_cost"] == "200.00"
    assert data["estimated_profit"] == "20.00"
    owned_data = client.get(f"/api/reports/seasons/{owned.season_id}/summary").json()
    assert owned_data["purchase_cost"] == "0.00"


def test_zero_payment_and_multiple_people_overview(report_client):
    client, db = report_client
    first = seed_core(db)
    second = seed_core_second(db)
    first_customer = Customer(customer_name="Buyer A")
    second_customer = Customer(customer_name="Buyer B")
    first_worker = Worker(worker_name="Worker A")
    second_worker = Worker(worker_name="Worker B")
    db.add_all([first_customer, second_customer, first_worker, second_worker])
    db.flush()
    seed_sales(db, first, first_customer)
    second_harvest = Harvest(
        season_id=second.season_id,
        harvest_date=date(2026, 9, 10),
        quantity_kg=Decimal("50.00"),
    )
    db.add(second_harvest)
    db.flush()
    db.add_all([
        Sale(harvest_id=second_harvest.harvest_id, customer_id=second_customer.customer_id, sale_date=date(2026, 9, 11), quantity_kg=Decimal("10.00"), unit_price=Decimal("5.00"), total_amount=Decimal("50.00")),
        LaborRecord(worker_id=first_worker.worker_id, season_id=first.season_id, work_date=date(2026, 9, 2), work_type="Pruning", amount=Decimal("40.00")),
        LaborRecord(worker_id=second_worker.worker_id, season_id=second.season_id, work_date=date(2026, 9, 11), work_type="Harvesting", amount=Decimal("20.00")),
        CustomerPayment(customer_id=first_customer.customer_id, payment_date=date(2026, 9, 12), amount=Decimal("100.00")),
        WorkerPayment(worker_id=first_worker.worker_id, payment_date=date(2026, 9, 12), amount=Decimal("15.00")),
    ])
    db.commit()

    customer_rows = client.get("/api/reports/customer-receivables").json()
    assert customer_rows[1]["total_payments"] == "0.00"
    assert customer_rows[1]["outstanding_amount"] == "50.00"
    worker_rows = client.get("/api/reports/worker-payables").json()
    assert worker_rows[1]["total_payments"] == "0.00"
    assert worker_rows[1]["outstanding_amount"] == "20.00"
    overview = client.get("/api/reports/overview").json()
    assert overview["total_harvest_kg"] == "150.00"
    assert overview["total_sold_kg"] == "40.00"
    assert overview["total_sales_revenue"] == "350.00"
    assert overview["total_customer_payments"] == "100.00"
    assert overview["total_customer_receivables"] == "250.00"
    assert overview["total_labor_cost"] == "60.00"
    assert overview["total_worker_payments"] == "15.00"
    assert overview["total_worker_payables"] == "45.00"
    assert overview["estimated_profit"] == "90.00"


def seed_core_second(db: Session):
    garden = Garden(garden_name="Garden B")
    variety = GrapeVariety(variety_name="Grape B")
    db.add_all([garden, variety])
    db.flush()
    season = Season(
        garden_id=garden.garden_id,
        variety_id=variety.variety_id,
        acquisition_type="OWNED",
        status="ACTIVE",
    )
    db.add(season)
    db.flush()
    return season
