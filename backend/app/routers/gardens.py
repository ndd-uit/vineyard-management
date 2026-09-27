from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.garden import Garden
from app.routers._database import commit_or_conflict
from app.schemas.garden import GardenCreate, GardenRead, GardenUpdate


router = APIRouter(prefix="/api/gardens", tags=["gardens"])


@router.get("", response_model=list[GardenRead])
def list_gardens(db: Session = Depends(get_db)):
    return db.scalars(select(Garden).order_by(Garden.garden_id)).all()


@router.get("/{garden_id}", response_model=GardenRead)
def get_garden(garden_id: int, db: Session = Depends(get_db)):
    garden = db.get(Garden, garden_id)
    if garden is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Garden not found")
    return garden


@router.post("", response_model=GardenRead, status_code=status.HTTP_201_CREATED)
def create_garden(payload: GardenCreate, db: Session = Depends(get_db)):
    garden = Garden(**payload.model_dump())
    db.add(garden)
    db.commit()
    db.refresh(garden)
    return garden


@router.patch("/{garden_id}", response_model=GardenRead)
def update_garden(
    garden_id: int, payload: GardenUpdate, db: Session = Depends(get_db)
):
    garden = get_garden(garden_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(garden, field, value)
    db.commit()
    db.refresh(garden)
    return garden


@router.delete("/{garden_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_garden(garden_id: int, db: Session = Depends(get_db)):
    garden = get_garden(garden_id, db)
    db.delete(garden)
    commit_or_conflict(db, "Garden is referenced by another record")
