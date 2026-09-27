from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.sale import Sale
from app.routers._database import commit_or_conflict
from app.schemas.sale import SaleCreate, SaleRead, SaleUpdate
from app.services.sale import validate_sale_and_total


router = APIRouter(prefix="/api/sales", tags=["sales"])


@router.get("", response_model=list[SaleRead])
def list_sales(db: Session = Depends(get_db)):
    return db.scalars(select(Sale).order_by(Sale.sale_id)).all()


@router.get("/{sale_id}", response_model=SaleRead)
def get_sale(sale_id: int, db: Session = Depends(get_db)):
    sale = db.get(Sale, sale_id)
    if sale is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sale not found")
    return sale


@router.post("", response_model=SaleRead, status_code=status.HTTP_201_CREATED)
def create_sale(payload: SaleCreate, db: Session = Depends(get_db)):
    values = payload.model_dump()
    total = validate_sale_and_total(
        db,
        harvest_id=payload.harvest_id,
        customer_id=payload.customer_id,
        quantity_kg=payload.quantity_kg,
        unit_price=payload.unit_price,
    )
    sale = Sale(**values, total_amount=total)
    db.add(sale)
    commit_or_conflict(db, "Sale references a missing record")
    db.refresh(sale)
    return sale


@router.patch("/{sale_id}", response_model=SaleRead)
def update_sale(sale_id: int, payload: SaleUpdate, db: Session = Depends(get_db)):
    sale = get_sale(sale_id, db)
    changes = payload.model_dump(exclude_unset=True)
    total = validate_sale_and_total(
        db,
        harvest_id=changes.get("harvest_id", sale.harvest_id),
        customer_id=changes.get("customer_id", sale.customer_id),
        quantity_kg=changes.get("quantity_kg", sale.quantity_kg),
        unit_price=changes.get("unit_price", sale.unit_price),
        exclude_sale_id=sale_id,
    )
    for field, value in changes.items():
        setattr(sale, field, value)
    sale.total_amount = total
    commit_or_conflict(db, "Sale update conflicts with related records")
    db.refresh(sale)
    return sale


@router.delete("/{sale_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sale(sale_id: int, db: Session = Depends(get_db)):
    sale = get_sale(sale_id, db)
    db.delete(sale)
    db.commit()
