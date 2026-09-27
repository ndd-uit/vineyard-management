from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.report import (
    CustomerReceivableDetail,
    CustomerReceivableSummary,
    OverviewSummary,
    SeasonSummary,
    WorkerPayableDetail,
    WorkerPayableSummary,
)
from app.services import report


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/customer-receivables", response_model=list[CustomerReceivableSummary])
def list_customer_receivables(db: Session = Depends(get_db)):
    return report.customer_receivables(db)


@router.get("/customer-receivables/{customer_id}", response_model=CustomerReceivableDetail)
def get_customer_receivable(customer_id: int, db: Session = Depends(get_db)):
    result = report.customer_receivable(db, customer_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return result


@router.get("/worker-payables", response_model=list[WorkerPayableSummary])
def list_worker_payables(db: Session = Depends(get_db)):
    return report.worker_payables(db)


@router.get("/worker-payables/{worker_id}", response_model=WorkerPayableDetail)
def get_worker_payable(worker_id: int, db: Session = Depends(get_db)):
    result = report.worker_payable(db, worker_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Worker not found")
    return result


@router.get("/seasons/{season_id}/summary", response_model=SeasonSummary)
def get_season_summary(season_id: int, db: Session = Depends(get_db)):
    result = report.season_summary(db, season_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Season not found")
    return result


@router.get("/overview", response_model=OverviewSummary)
def get_overview(db: Session = Depends(get_db)):
    return report.overview(db)
