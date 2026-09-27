from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.worker import Worker
from app.routers._database import commit_or_conflict
from app.schemas.worker import WorkerCreate, WorkerRead, WorkerUpdate


router = APIRouter(prefix="/api/workers", tags=["workers"])


@router.get("", response_model=list[WorkerRead])
def list_workers(db: Session = Depends(get_db)):
    return db.scalars(select(Worker).order_by(Worker.worker_id)).all()


@router.get("/{worker_id}", response_model=WorkerRead)
def get_worker(worker_id: int, db: Session = Depends(get_db)):
    worker = db.get(Worker, worker_id)
    if worker is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Worker not found")
    return worker


@router.post("", response_model=WorkerRead, status_code=status.HTTP_201_CREATED)
def create_worker(payload: WorkerCreate, db: Session = Depends(get_db)):
    worker = Worker(**payload.model_dump())
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return worker


@router.patch("/{worker_id}", response_model=WorkerRead)
def update_worker(worker_id: int, payload: WorkerUpdate, db: Session = Depends(get_db)):
    worker = get_worker(worker_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(worker, field, value)
    db.commit()
    db.refresh(worker)
    return worker


@router.delete("/{worker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_worker(worker_id: int, db: Session = Depends(get_db)):
    worker = get_worker(worker_id, db)
    db.delete(worker)
    commit_or_conflict(db, "Worker is referenced by another record")
