from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.season import Season
from app.routers._database import commit_or_conflict
from app.schemas.season import SeasonCreate, SeasonRead, SeasonUpdate
from app.services.season import validate_season


router = APIRouter(prefix="/api/seasons", tags=["seasons"])


@router.get("", response_model=list[SeasonRead])
def list_seasons(db: Session = Depends(get_db)):
    return db.scalars(select(Season).order_by(Season.season_id)).all()


@router.get("/{season_id}", response_model=SeasonRead)
def get_season(season_id: int, db: Session = Depends(get_db)):
    season = db.get(Season, season_id)
    if season is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Season not found")
    return season


@router.post("", response_model=SeasonRead, status_code=status.HTTP_201_CREATED)
def create_season(payload: SeasonCreate, db: Session = Depends(get_db)):
    values = payload.model_dump()
    validate_season(
        db,
        garden_id=values["garden_id"],
        variety_id=values["variety_id"],
        start_date=values["start_date"],
        end_date=values["end_date"],
        acquisition_type=values["acquisition_type"],
        purchase_price=values["purchase_price"],
    )
    season = Season(**values)
    db.add(season)
    db.commit()
    db.refresh(season)
    return season


@router.patch("/{season_id}", response_model=SeasonRead)
def update_season(
    season_id: int, payload: SeasonUpdate, db: Session = Depends(get_db)
):
    season = get_season(season_id, db)
    changes = payload.model_dump(exclude_unset=True)
    values = {
        "garden_id": changes.get("garden_id", season.garden_id),
        "variety_id": changes.get("variety_id", season.variety_id),
        "start_date": changes.get("start_date", season.start_date),
        "end_date": changes.get("end_date", season.end_date),
        "acquisition_type": changes.get("acquisition_type", season.acquisition_type),
        "purchase_price": changes.get("purchase_price", season.purchase_price),
    }
    validate_season(db, **values)
    for field, value in changes.items():
        setattr(season, field, value)
    db.commit()
    db.refresh(season)
    return season


@router.delete("/{season_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_season(season_id: int, db: Session = Depends(get_db)):
    season = get_season(season_id, db)
    db.delete(season)
    commit_or_conflict(db, "Season is referenced by another record")
