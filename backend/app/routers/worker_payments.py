from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.worker import Worker
from app.models.worker_payment import WorkerPayment
from app.routers._database import commit_or_conflict
from app.schemas.worker_payment import (
    WorkerPaymentCreate,
    WorkerPaymentRead,
    WorkerPaymentUpdate,
)


router = APIRouter(prefix="/api/worker-payments", tags=["worker payments"])


def require_worker(db: Session, worker_id: int) -> None:
    if db.get(Worker, worker_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "worker_id does not exist")


@router.get("", response_model=list[WorkerPaymentRead])
def list_worker_payments(db: Session = Depends(get_db)):
    return db.scalars(
        select(WorkerPayment).order_by(WorkerPayment.worker_payment_id)
    ).all()


@router.get("/{worker_payment_id}", response_model=WorkerPaymentRead)
def get_worker_payment(worker_payment_id: int, db: Session = Depends(get_db)):
    payment = db.get(WorkerPayment, worker_payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Worker payment not found")
    return payment


@router.post("", response_model=WorkerPaymentRead, status_code=status.HTTP_201_CREATED)
def create_worker_payment(
    payload: WorkerPaymentCreate, db: Session = Depends(get_db)
):
    require_worker(db, payload.worker_id)
    payment = WorkerPayment(**payload.model_dump())
    db.add(payment)
    commit_or_conflict(db, "Worker payment references a missing worker")
    db.refresh(payment)
    return payment


@router.patch("/{worker_payment_id}", response_model=WorkerPaymentRead)
def update_worker_payment(
    worker_payment_id: int,
    payload: WorkerPaymentUpdate,
    db: Session = Depends(get_db),
):
    payment = get_worker_payment(worker_payment_id, db)
    changes = payload.model_dump(exclude_unset=True)
    if "worker_id" in changes:
        require_worker(db, changes["worker_id"])
    for field, value in changes.items():
        setattr(payment, field, value)
    commit_or_conflict(db, "Worker payment references a missing worker")
    db.refresh(payment)
    return payment


@router.delete("/{worker_payment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_worker_payment(worker_payment_id: int, db: Session = Depends(get_db)):
    payment = get_worker_payment(worker_payment_id, db)
    db.delete(payment)
    db.commit()
