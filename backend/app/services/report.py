from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
from app.schemas.report import (
    CustomerReceivableDetail,
    CustomerReceivableSummary,
    CustomerTransaction,
    OverviewSummary,
    SeasonSummary,
    WorkerLaborTransaction,
    WorkerPayableDetail,
    WorkerPayableSummary,
    WorkerPaymentTransaction,
)


def _amount(value: Decimal | None) -> Decimal:
    return value if value is not None else Decimal("0.00")


def _sum(db: Session, column, *conditions) -> Decimal:
    return _amount(db.scalar(select(func.sum(column)).where(*conditions)))


def _customer_totals_query():
    sales = (
        select(Sale.customer_id, func.sum(Sale.total_amount).label("total_sales"))
        .group_by(Sale.customer_id)
        .subquery()
    )
    payments = (
        select(
            CustomerPayment.customer_id,
            func.sum(CustomerPayment.amount).label("total_payments"),
        )
        .group_by(CustomerPayment.customer_id)
        .subquery()
    )
    return (
        select(
            Customer.customer_id,
            Customer.customer_name,
            sales.c.total_sales,
            payments.c.total_payments,
        )
        .outerjoin(sales, Customer.customer_id == sales.c.customer_id)
        .outerjoin(payments, Customer.customer_id == payments.c.customer_id)
    )


def _customer_summary(row) -> CustomerReceivableSummary:
    sales = _amount(row.total_sales)
    payments = _amount(row.total_payments)
    return CustomerReceivableSummary(
        customer_id=row.customer_id,
        customer_name=row.customer_name,
        total_sales=sales,
        total_payments=payments,
        outstanding_amount=sales - payments,
    )


def customer_receivables(db: Session) -> list[CustomerReceivableSummary]:
    rows = db.execute(_customer_totals_query().order_by(Customer.customer_id))
    return [_customer_summary(row) for row in rows]


def customer_receivable(db: Session, customer_id: int) -> CustomerReceivableDetail | None:
    row = db.execute(
        _customer_totals_query().where(Customer.customer_id == customer_id)
    ).one_or_none()
    if row is None:
        return None

    history = [
        CustomerTransaction(
            date=sale.sale_date,
            type="SALE",
            reference_id=sale.sale_id,
            amount=sale.total_amount,
        )
        for sale in db.scalars(select(Sale).where(Sale.customer_id == customer_id))
    ]
    history.extend(
        CustomerTransaction(
            date=payment.payment_date,
            type="PAYMENT",
            reference_id=payment.payment_id,
            amount=payment.amount,
        )
        for payment in db.scalars(
            select(CustomerPayment).where(CustomerPayment.customer_id == customer_id)
        )
    )
    history.sort(key=lambda entry: (entry.date, entry.type, entry.reference_id))
    return CustomerReceivableDetail(**_customer_summary(row).model_dump(), history=history)


def _worker_totals_query():
    labor = (
        select(LaborRecord.worker_id, func.sum(LaborRecord.amount).label("total_labor"))
        .group_by(LaborRecord.worker_id)
        .subquery()
    )
    payments = (
        select(
            WorkerPayment.worker_id,
            func.sum(WorkerPayment.amount).label("total_payments"),
        )
        .group_by(WorkerPayment.worker_id)
        .subquery()
    )
    return (
        select(
            Worker.worker_id,
            Worker.worker_name,
            labor.c.total_labor,
            payments.c.total_payments,
        )
        .outerjoin(labor, Worker.worker_id == labor.c.worker_id)
        .outerjoin(payments, Worker.worker_id == payments.c.worker_id)
    )


def _worker_summary(row) -> WorkerPayableSummary:
    labor = _amount(row.total_labor)
    payments = _amount(row.total_payments)
    return WorkerPayableSummary(
        worker_id=row.worker_id,
        worker_name=row.worker_name,
        total_labor=labor,
        total_payments=payments,
        outstanding_amount=labor - payments,
    )


def worker_payables(db: Session) -> list[WorkerPayableSummary]:
    rows = db.execute(_worker_totals_query().order_by(Worker.worker_id))
    return [_worker_summary(row) for row in rows]


def worker_payable(db: Session, worker_id: int) -> WorkerPayableDetail | None:
    row = db.execute(
        _worker_totals_query().where(Worker.worker_id == worker_id)
    ).one_or_none()
    if row is None:
        return None

    history: list[WorkerLaborTransaction | WorkerPaymentTransaction] = [
        WorkerLaborTransaction(
            work_date=labor.work_date,
            reference_id=labor.labor_id,
            work_type=labor.work_type,
            amount=labor.amount,
        )
        for labor in db.scalars(
            select(LaborRecord).where(LaborRecord.worker_id == worker_id)
        )
    ]
    history.extend(
        WorkerPaymentTransaction(
            payment_date=payment.payment_date,
            reference_id=payment.worker_payment_id,
            amount=payment.amount,
        )
        for payment in db.scalars(
            select(WorkerPayment).where(WorkerPayment.worker_id == worker_id)
        )
    )
    history.sort(
        key=lambda entry: (
            entry.work_date if isinstance(entry, WorkerLaborTransaction) else entry.payment_date,
            entry.type,
            entry.reference_id,
        )
    )
    return WorkerPayableDetail(**_worker_summary(row).model_dump(), history=history)


def season_summary(db: Session, season_id: int) -> SeasonSummary | None:
    row = db.execute(
        select(Season, Garden.garden_name, GrapeVariety.variety_name)
        .join(Garden, Garden.garden_id == Season.garden_id)
        .join(GrapeVariety, GrapeVariety.variety_id == Season.variety_id)
        .where(Season.season_id == season_id)
    ).one_or_none()
    if row is None:
        return None

    season, garden_name, variety_name = row
    harvest_kg = _sum(db, Harvest.quantity_kg, Harvest.season_id == season_id)
    sold_kg, sales_revenue = db.execute(
        select(func.sum(Sale.quantity_kg), func.sum(Sale.total_amount))
        .join(Harvest, Harvest.harvest_id == Sale.harvest_id)
        .where(Harvest.season_id == season_id)
    ).one()
    sold_kg = _amount(sold_kg)
    sales_revenue = _amount(sales_revenue)
    expenses = _sum(db, Expense.amount, Expense.season_id == season_id)
    labor = _sum(db, LaborRecord.amount, LaborRecord.season_id == season_id)
    purchase = _amount(season.purchase_price)
    total_cost = purchase + expenses + labor
    return SeasonSummary(
        season_id=season.season_id,
        season_name=season.season_name,
        garden_id=season.garden_id,
        garden_name=garden_name,
        variety_id=season.variety_id,
        variety_name=variety_name,
        acquisition_type=season.acquisition_type,
        status=season.status,
        total_harvest_kg=harvest_kg,
        total_sold_kg=sold_kg,
        remaining_kg=harvest_kg - sold_kg,
        sales_revenue=sales_revenue,
        purchase_cost=purchase,
        operating_expenses=expenses,
        labor_cost=labor,
        total_cost=total_cost,
        estimated_profit=sales_revenue - total_cost,
    )


def overview(db: Session) -> OverviewSummary:
    harvest_kg = _sum(db, Harvest.quantity_kg)
    sold_kg, revenue = db.execute(
        select(func.sum(Sale.quantity_kg), func.sum(Sale.total_amount))
    ).one()
    sold_kg = _amount(sold_kg)
    revenue = _amount(revenue)
    customer_payments = _sum(db, CustomerPayment.amount)
    labor = _sum(db, LaborRecord.amount)
    worker_payments = _sum(db, WorkerPayment.amount)
    expenses = _sum(db, Expense.amount)
    purchase = _sum(db, Season.purchase_price)
    return OverviewSummary(
        total_harvest_kg=harvest_kg,
        total_sold_kg=sold_kg,
        remaining_kg=harvest_kg - sold_kg,
        total_sales_revenue=revenue,
        total_customer_payments=customer_payments,
        total_customer_receivables=revenue - customer_payments,
        total_labor_cost=labor,
        total_worker_payments=worker_payments,
        total_worker_payables=labor - worker_payments,
        total_operating_expenses=expenses,
        total_purchase_cost=purchase,
        estimated_profit=revenue - purchase - expenses - labor,
    )
