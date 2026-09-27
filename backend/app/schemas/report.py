from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.models.season import AcquisitionType, SeasonStatus


class CustomerReceivableSummary(BaseModel):
    customer_id: int
    customer_name: str
    total_sales: Decimal
    total_payments: Decimal
    outstanding_amount: Decimal


class CustomerTransaction(BaseModel):
    date: date
    type: Literal["SALE", "PAYMENT"]
    reference_id: int
    amount: Decimal


class CustomerReceivableDetail(CustomerReceivableSummary):
    history: list[CustomerTransaction]


class WorkerPayableSummary(BaseModel):
    worker_id: int
    worker_name: str
    total_labor: Decimal
    total_payments: Decimal
    outstanding_amount: Decimal


class WorkerLaborTransaction(BaseModel):
    work_date: date
    type: Literal["LABOR"] = "LABOR"
    reference_id: int
    work_type: str
    amount: Decimal


class WorkerPaymentTransaction(BaseModel):
    payment_date: date
    type: Literal["PAYMENT"] = "PAYMENT"
    reference_id: int
    amount: Decimal


class WorkerPayableDetail(WorkerPayableSummary):
    history: list[WorkerLaborTransaction | WorkerPaymentTransaction]


class SeasonSummary(BaseModel):
    season_id: int
    season_name: str | None
    garden_id: int
    garden_name: str
    variety_id: int
    variety_name: str
    acquisition_type: AcquisitionType
    status: SeasonStatus
    total_harvest_kg: Decimal
    total_sold_kg: Decimal
    remaining_kg: Decimal
    sales_revenue: Decimal
    purchase_cost: Decimal
    operating_expenses: Decimal
    labor_cost: Decimal
    total_cost: Decimal
    estimated_profit: Decimal


class OverviewSummary(BaseModel):
    total_harvest_kg: Decimal
    total_sold_kg: Decimal
    remaining_kg: Decimal
    total_sales_revenue: Decimal
    total_customer_payments: Decimal
    total_customer_receivables: Decimal
    total_labor_cost: Decimal
    total_worker_payments: Decimal
    total_worker_payables: Decimal
    total_operating_expenses: Decimal
    total_purchase_cost: Decimal
    estimated_profit: Decimal
