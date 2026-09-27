from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.harvest import Harvest
from app.models.season import Season
from app.routers._database import commit_or_conflict
from app.schemas.harvest import HarvestCreate, HarvestRead, HarvestUpdate
from app.services.sale import validate_harvest_quantity


router = APIRouter(prefix="/api/harvests", tags=["harvests"])


def require_season(db: Session, season_id: int) -> None:
    if db.get(Season, season_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "season_id does not exist")


@router.get("", response_model=list[HarvestRead])
def list_harvests(db: Session = Depends(get_db)):
    return db.scalars(select(Harvest).order_by(Harvest.harvest_id)).all()


@router.get("/{harvest_id}", response_model=HarvestRead)
def get_harvest(harvest_id: int, db: Session = Depends(get_db)):
    harvest = db.get(Harvest, harvest_id)
    if harvest is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Harvest not found")
    return harvest


@router.post("", response_model=HarvestRead, status_code=status.HTTP_201_CREATED)
def create_harvest(payload: HarvestCreate, db: Session = Depends(get_db)):
    require_season(db, payload.season_id)
    harvest = Harvest(**payload.model_dump())
    db.add(harvest)
    commit_or_conflict(db, "Harvest references a missing season")
    db.refresh(harvest)
    return harvest


@router.patch("/{harvest_id}", response_model=HarvestRead)
def update_harvest(
    harvest_id: int, payload: HarvestUpdate, db: Session = Depends(get_db)
):
    harvest = get_harvest(harvest_id, db)
    changes = payload.model_dump(exclude_unset=True)
    if "season_id" in changes:
        require_season(db, changes["season_id"])
    if "quantity_kg" in changes:
        validate_harvest_quantity(db, harvest_id, changes["quantity_kg"])
    for field, value in changes.items():
        setattr(harvest, field, value)
    commit_or_conflict(db, "Harvest update conflicts with related records")
    db.refresh(harvest)
    return harvest


@router.delete("/{harvest_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_harvest(harvest_id: int, db: Session = Depends(get_db)):
    harvest = get_harvest(harvest_id, db)
    db.delete(harvest)
    commit_or_conflict(db, "Harvest is referenced by another record")
