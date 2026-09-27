from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.grape_variety import GrapeVariety
from app.routers._database import commit_or_conflict
from app.schemas.grape_variety import (
    GrapeVarietyCreate,
    GrapeVarietyRead,
    GrapeVarietyUpdate,
)


router = APIRouter(prefix="/api/grape-varieties", tags=["grape varieties"])


@router.get("", response_model=list[GrapeVarietyRead])
def list_grape_varieties(db: Session = Depends(get_db)):
    return db.scalars(select(GrapeVariety).order_by(GrapeVariety.variety_id)).all()


@router.get("/{variety_id}", response_model=GrapeVarietyRead)
def get_grape_variety(variety_id: int, db: Session = Depends(get_db)):
    variety = db.get(GrapeVariety, variety_id)
    if variety is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grape variety not found")
    return variety


@router.post("", response_model=GrapeVarietyRead, status_code=status.HTTP_201_CREATED)
def create_grape_variety(
    payload: GrapeVarietyCreate, db: Session = Depends(get_db)
):
    variety = GrapeVariety(**payload.model_dump())
    db.add(variety)
    commit_or_conflict(db, "Grape variety name already exists")
    db.refresh(variety)
    return variety


@router.patch("/{variety_id}", response_model=GrapeVarietyRead)
def update_grape_variety(
    variety_id: int, payload: GrapeVarietyUpdate, db: Session = Depends(get_db)
):
    variety = get_grape_variety(variety_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(variety, field, value)
    commit_or_conflict(db, "Grape variety name already exists")
    db.refresh(variety)
    return variety


@router.delete("/{variety_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_grape_variety(variety_id: int, db: Session = Depends(get_db)):
    variety = get_grape_variety(variety_id, db)
    db.delete(variety)
    commit_or_conflict(db, "Grape variety is referenced by another record")
