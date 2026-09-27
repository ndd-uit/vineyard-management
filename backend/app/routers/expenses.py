from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.expense import Expense
from app.models.season import Season
from app.routers._database import commit_or_conflict
from app.schemas.expense import ExpenseCreate, ExpenseRead, ExpenseUpdate
from app.services.expense import validate_expense_category


router = APIRouter(prefix="/api/expenses", tags=["expenses"])


def require_season(db: Session, season_id: int) -> None:
    if db.get(Season, season_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "season_id does not exist")


@router.get("", response_model=list[ExpenseRead])
def list_expenses(db: Session = Depends(get_db)):
    return db.scalars(select(Expense).order_by(Expense.expense_id)).all()


@router.get("/{expense_id}", response_model=ExpenseRead)
def get_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found")
    return expense


@router.post("", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
def create_expense(payload: ExpenseCreate, db: Session = Depends(get_db)):
    require_season(db, payload.season_id)
    validate_expense_category(payload.category)
    expense = Expense(**payload.model_dump())
    db.add(expense)
    commit_or_conflict(db, "Expense references a missing season")
    db.refresh(expense)
    return expense


@router.patch("/{expense_id}", response_model=ExpenseRead)
def update_expense(
    expense_id: int, payload: ExpenseUpdate, db: Session = Depends(get_db)
):
    expense = get_expense(expense_id, db)
    changes = payload.model_dump(exclude_unset=True)
    if "season_id" in changes:
        require_season(db, changes["season_id"])
    if "category" in changes:
        validate_expense_category(changes["category"])
    for field, value in changes.items():
        setattr(expense, field, value)
    commit_or_conflict(db, "Expense references a missing season")
    db.refresh(expense)
    return expense


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = get_expense(expense_id, db)
    db.delete(expense)
    db.commit()
