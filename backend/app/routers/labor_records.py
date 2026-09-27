from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.labor_record import LaborRecord
from app.models.season import Season
from app.models.worker import Worker
from app.routers._database import commit_or_conflict
from app.schemas.labor_record import (
    LaborRecordCreate,
    LaborRecordRead,
    LaborRecordUpdate,
)


router = APIRouter(prefix="/api/labor-records", tags=["labor records"])


def require_labor_references(db: Session, worker_id: int, season_id: int) -> None:
    if db.get(Worker, worker_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "worker_id does not exist")
    if db.get(Season, season_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "season_id does not exist")


@router.get("", response_model=list[LaborRecordRead])
def list_labor_records(db: Session = Depends(get_db)):
    return db.scalars(select(LaborRecord).order_by(LaborRecord.labor_id)).all()


@router.get("/{labor_id}", response_model=LaborRecordRead)
def get_labor_record(labor_id: int, db: Session = Depends(get_db)):
    labor = db.get(LaborRecord, labor_id)
    if labor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Labor record not found")
    return labor


@router.post("", response_model=LaborRecordRead, status_code=status.HTTP_201_CREATED)
def create_labor_record(
    payload: LaborRecordCreate, db: Session = Depends(get_db)
):
    require_labor_references(db, payload.worker_id, payload.season_id)
    labor = LaborRecord(**payload.model_dump())
    db.add(labor)
    commit_or_conflict(db, "Labor record references a missing record")
    db.refresh(labor)
    return labor


@router.patch("/{labor_id}", response_model=LaborRecordRead)
def update_labor_record(
    labor_id: int, payload: LaborRecordUpdate, db: Session = Depends(get_db)
):
    labor = get_labor_record(labor_id, db)
    changes = payload.model_dump(exclude_unset=True)
    if "worker_id" in changes or "season_id" in changes:
        require_labor_references(
            db,
            changes.get("worker_id", labor.worker_id),
            changes.get("season_id", labor.season_id),
        )
    for field, value in changes.items():
        setattr(labor, field, value)
    commit_or_conflict(db, "Labor record references a missing record")
    db.refresh(labor)
    return labor


@router.delete("/{labor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_labor_record(labor_id: int, db: Session = Depends(get_db)):
    labor = get_labor_record(labor_id, db)
    db.delete(labor)
    db.commit()
