from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.harvest import Harvest
from app.models.sale import Sale


def sold_quantity(
    db: Session, harvest_id: int, exclude_sale_id: int | None = None
) -> Decimal:
    statement = select(func.coalesce(func.sum(Sale.quantity_kg), 0)).where(
        Sale.harvest_id == harvest_id
    )
    if exclude_sale_id is not None:
        statement = statement.where(Sale.sale_id != exclude_sale_id)
    return Decimal(db.scalar(statement))


def validate_harvest_quantity(
    db: Session, harvest_id: int, quantity_kg: Decimal
) -> None:
    # Sale writes lock the same row, so an edit cannot reduce quantity mid-sale.
    db.scalar(select(Harvest).where(Harvest.harvest_id == harvest_id).with_for_update())
    if sold_quantity(db, harvest_id) > quantity_kg:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Harvest quantity cannot be less than quantity already sold",
        )


def validate_sale_and_total(
    db: Session,
    *,
    harvest_id: int,
    customer_id: int,
    quantity_kg: Decimal,
    unit_price: Decimal,
    exclude_sale_id: int | None = None,
) -> Decimal:
    # PostgreSQL holds this lock until commit, serializing sales of one harvest.
    harvest = db.scalar(
        select(Harvest).where(Harvest.harvest_id == harvest_id).with_for_update()
    )
    if harvest is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "harvest_id does not exist")
    if db.get(Customer, customer_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "customer_id does not exist")

    if sold_quantity(db, harvest_id, exclude_sale_id) + quantity_kg > harvest.quantity_kg:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Sale quantity exceeds the harvest quantity available",
        )

    total = (quantity_kg * unit_price).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if total > Decimal("9999999999999.99"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "total_amount exceeds numeric(15,2)",
        )
    return total
