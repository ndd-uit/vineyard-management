from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.customer import Customer
from app.models.customer_payment import CustomerPayment
from app.routers._database import commit_or_conflict
from app.schemas.customer_payment import (
    CustomerPaymentCreate,
    CustomerPaymentRead,
    CustomerPaymentUpdate,
)


router = APIRouter(prefix="/api/customer-payments", tags=["customer payments"])


def require_customer(db: Session, customer_id: int) -> None:
    if db.get(Customer, customer_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "customer_id does not exist")


@router.get("", response_model=list[CustomerPaymentRead])
def list_customer_payments(db: Session = Depends(get_db)):
    return db.scalars(
        select(CustomerPayment).order_by(CustomerPayment.payment_id)
    ).all()


@router.get("/{payment_id}", response_model=CustomerPaymentRead)
def get_customer_payment(payment_id: int, db: Session = Depends(get_db)):
    payment = db.get(CustomerPayment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer payment not found")
    return payment


@router.post("", response_model=CustomerPaymentRead, status_code=status.HTTP_201_CREATED)
def create_customer_payment(
    payload: CustomerPaymentCreate, db: Session = Depends(get_db)
):
    require_customer(db, payload.customer_id)
    payment = CustomerPayment(**payload.model_dump())
    db.add(payment)
    commit_or_conflict(db, "Customer payment references a missing customer")
    db.refresh(payment)
    return payment


@router.patch("/{payment_id}", response_model=CustomerPaymentRead)
def update_customer_payment(
    payment_id: int, payload: CustomerPaymentUpdate, db: Session = Depends(get_db)
):
    payment = get_customer_payment(payment_id, db)
    changes = payload.model_dump(exclude_unset=True)
    if "customer_id" in changes:
        require_customer(db, changes["customer_id"])
    for field, value in changes.items():
        setattr(payment, field, value)
    commit_or_conflict(db, "Customer payment references a missing customer")
    db.refresh(payment)
    return payment


@router.delete("/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer_payment(payment_id: int, db: Session = Depends(get_db)):
    payment = get_customer_payment(payment_id, db)
    db.delete(payment)
    db.commit()
