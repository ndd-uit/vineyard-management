from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any
import unicodedata

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Customer,
    CustomerPayment,
    Expense,
    Garden,
    GrapeVariety,
    Harvest,
    LaborRecord,
    Sale,
    Season,
    Worker,
    WorkerPayment,
)
from app.routers._database import commit_or_conflict
from app.schemas.assistant_actions import (
    ActionExecutionResult,
    CreateCustomer,
    CreateGarden,
    CreateGrapeVariety,
    CreateSeason,
    CreateWorker,
    FindCustomers,
    FindGardens,
    FindGrapeVarieties,
    FindHarvests,
    FindSeasons,
    FindWorkers,
    GetBusinessOverview,
    GetCustomerReceivable,
    GetSeasonSummary,
    GetWorkerPayable,
    HarvestLookupRead,
    PendingActionPreview,
    QueryResult,
    ReadAction,
    RecordCustomerPayment,
    RecordExpense,
    RecordHarvest,
    RecordLabor,
    RecordSale,
    RecordWorkerPayment,
    WriteAction,
)
from app.schemas.customer import CustomerRead
from app.schemas.garden import GardenRead
from app.schemas.grape_variety import GrapeVarietyRead
from app.schemas.season import SeasonRead
from app.schemas.worker import WorkerRead
from app.services import report
from app.services import action_tokens
from app.services.assistant_presentation import action_summary
from app.services.expense import validate_expense_category
from app.services.sale import validate_sale_and_total
from app.services.season import validate_season


def _require(db: Session, model: type, identifier: int, field: str):
    entity = db.get(model, identifier)
    if entity is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{field} does not exist")
    return entity


def _validate_write(db: Session, request: WriteAction) -> tuple[str, dict[str, Any]]:
    args = request.arguments
    derived: dict[str, Any] = {}
    if isinstance(request, RecordHarvest):
        _require(db, Season, args.season_id, "season_id")
    elif isinstance(request, RecordSale):
        derived["total_amount"] = validate_sale_and_total(
            db,
            harvest_id=args.harvest_id,
            customer_id=args.customer_id,
            quantity_kg=args.quantity_kg,
            unit_price=args.unit_price,
        )
        _require(db, Customer, args.customer_id, "customer_id")
    elif isinstance(request, RecordCustomerPayment):
        _require(db, Customer, args.customer_id, "customer_id")
    elif isinstance(request, RecordLabor):
        _require(db, Worker, args.worker_id, "worker_id")
        _require(db, Season, args.season_id, "season_id")
    elif isinstance(request, RecordWorkerPayment):
        _require(db, Worker, args.worker_id, "worker_id")
    elif isinstance(request, RecordExpense):
        _require(db, Season, args.season_id, "season_id")
        validate_expense_category(args.category)
    elif isinstance(request, CreateGrapeVariety):
        if likely_entity_duplicates(db, request.action, args.variety_name):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A similar grape variety already exists")
    elif isinstance(request, CreateSeason):
        validate_season(
            db,
            garden_id=args.garden_id,
            variety_id=args.variety_id,
            start_date=args.start_date,
            end_date=args.end_date,
            acquisition_type=args.acquisition_type,
            purchase_price=args.purchase_price,
        )
    elif not isinstance(request, (CreateCustomer, CreateWorker, CreateGarden)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unsupported action")
    return action_summary(db, request, derived), derived


_WRITE_TARGETS = {
    "record_harvest": (Harvest, "harvest_id"),
    "record_sale": (Sale, "sale_id"),
    "record_customer_payment": (CustomerPayment, "payment_id"),
    "record_labor": (LaborRecord, "labor_id"),
    "record_worker_payment": (WorkerPayment, "worker_payment_id"),
    "record_expense": (Expense, "expense_id"),
    "create_customer": (Customer, "customer_id"),
    "create_worker": (Worker, "worker_id"),
    "create_garden": (Garden, "garden_id"),
    "create_grape_variety": (GrapeVariety, "variety_id"),
    "create_season": (Season, "season_id"),
}


def preview(db: Session, request: WriteAction, *, user_id: str) -> PendingActionPreview:
    summary, derived = _validate_write(db, request)
    arguments = request.arguments.model_dump(mode="json", exclude_none=True)
    idempotency_key, expires_at = action_tokens.new_preview_identity()
    return PendingActionPreview(
        action=request.action,
        arguments=arguments,
        summary=summary,
        action_token=action_tokens.action_token(
            request, user_id=user_id, idempotency_key=idempotency_key, expires_at=expires_at
        ),
        idempotency_key=idempotency_key,
        expires_at=expires_at,
        calculated={key: str(value) for key, value in derived.items()},
    )


def execute_uncommitted(db: Session, request: WriteAction) -> ActionExecutionResult:
    if request.confirmed is not True:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "confirmed=true is required")
    # The caller's preview is never trusted: recheck references and quantities now.
    _, derived = _validate_write(db, request)
    model, id_field = _WRITE_TARGETS[request.action]
    instance = model(**request.arguments.model_dump(), **derived)
    db.add(instance)
    db.flush()
    result = request.arguments.model_dump(mode="json", exclude_none=True)
    result.update({key: str(value) for key, value in derived.items()})
    result[id_field] = getattr(instance, id_field)
    return ActionExecutionResult(
        action=request.action,
        resource_type=model.__tablename__,
        resource_id=getattr(instance, id_field),
        result=result,
        message="Con đã ghi lại rồi ạ.",
    )


def execute(db: Session, request: WriteAction) -> ActionExecutionResult:
    """Standalone wrapper retained for internal callers and existing tests."""
    try:
        result = execute_uncommitted(db, request)
        commit_or_conflict(db, "Action conflicts with related records")
        return result
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Action conflicts with related records") from exc


def _find(db: Session, model: type, name_column, id_column, name: str | None):
    statement = select(model)
    if name is not None:
        escaped = name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(name_column.ilike(f"%{escaped}%", escape="\\"))
    return db.scalars(statement.order_by(id_column)).all()


def _normalized_name(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name.casefold().replace("đ", "d"))
    without_marks = "".join(character for character in folded if not unicodedata.combining(character))
    return " ".join(without_marks.split())


def likely_entity_duplicates(db: Session, action: str, name: str) -> list[dict[str, Any]]:
    """Find likely existing entities before an assistant CREATE preview."""
    target = {
        "create_customer": (Customer, Customer.customer_id, Customer.customer_name),
        "create_worker": (Worker, Worker.worker_id, Worker.worker_name),
        "create_garden": (Garden, Garden.garden_id, Garden.garden_name),
        "create_grape_variety": (GrapeVariety, GrapeVariety.variety_id, GrapeVariety.variety_name),
    }.get(action)
    if target is None:
        return []
    model, id_column, name_column = target
    wanted = _normalized_name(name)
    matches = []
    for identifier, existing_name in db.execute(select(id_column, name_column).select_from(model)):
        candidate = _normalized_name(existing_name)
        if candidate == wanted or SequenceMatcher(None, candidate, wanted).ratio() >= 0.92:
            matches.append({"id": identifier, "name": existing_name})
    return matches


def _find_harvests(db: Session, arguments) -> list[HarvestLookupRead]:
    sold = (
        select(Sale.harvest_id, func.sum(Sale.quantity_kg).label("sold_kg"))
        .group_by(Sale.harvest_id)
        .subquery()
    )
    statement = (
        select(
            Harvest.harvest_id,
            Harvest.harvest_date,
            Harvest.quantity_kg,
            sold.c.sold_kg,
            Season.season_id,
            Season.season_name,
            Garden.garden_id,
            Garden.garden_name,
            GrapeVariety.variety_id,
            GrapeVariety.variety_name,
        )
        .join(Season, Season.season_id == Harvest.season_id)
        .join(Garden, Garden.garden_id == Season.garden_id)
        .join(GrapeVariety, GrapeVariety.variety_id == Season.variety_id)
        .outerjoin(sold, sold.c.harvest_id == Harvest.harvest_id)
    )
    if arguments.garden_id is not None:
        statement = statement.where(Garden.garden_id == arguments.garden_id)
    if arguments.season_id is not None:
        statement = statement.where(Season.season_id == arguments.season_id)
    if arguments.harvest_date is not None:
        statement = statement.where(Harvest.harvest_date == arguments.harvest_date)
    if arguments.date_from is not None:
        statement = statement.where(Harvest.harvest_date >= arguments.date_from)
    if arguments.date_to is not None:
        statement = statement.where(Harvest.harvest_date <= arguments.date_to)
    rows = db.execute(statement.order_by(Harvest.harvest_date.desc(), Harvest.harvest_id.desc()))
    result = []
    for row in rows:
        sold_kg = row.sold_kg if row.sold_kg is not None else Decimal("0.00")
        result.append(HarvestLookupRead(
            harvest_id=row.harvest_id,
            harvest_date=row.harvest_date,
            quantity_kg=row.quantity_kg,
            sold_quantity_kg=sold_kg,
            remaining_quantity_kg=row.quantity_kg - sold_kg,
            season_id=row.season_id,
            season_name=row.season_name,
            garden_id=row.garden_id,
            garden_name=row.garden_name,
            variety_id=row.variety_id,
            variety_name=row.variety_name,
        ))
    return result


def query(db: Session, request: ReadAction) -> QueryResult:
    if isinstance(request, FindGardens):
        found = _find(db, Garden, Garden.garden_name, Garden.garden_id, request.arguments.name)
        result = [GardenRead.model_validate(item) for item in found]
    elif isinstance(request, FindGrapeVarieties):
        found = db.scalars(select(GrapeVariety).order_by(GrapeVariety.variety_id)).all()
        if request.arguments.name is not None:
            wanted = _normalized_name(request.arguments.name)
            found = [item for item in found if wanted in _normalized_name(item.variety_name)]
        result = [GrapeVarietyRead.model_validate(item) for item in found]
    elif isinstance(request, FindSeasons):
        found = _find(db, Season, Season.season_name, Season.season_id, request.arguments.name)
        result = [SeasonRead.model_validate(item) for item in found]
    elif isinstance(request, FindCustomers):
        found = _find(db, Customer, Customer.customer_name, Customer.customer_id, request.arguments.name)
        result = [CustomerRead.model_validate(item) for item in found]
    elif isinstance(request, FindWorkers):
        found = _find(db, Worker, Worker.worker_name, Worker.worker_id, request.arguments.name)
        result = [WorkerRead.model_validate(item) for item in found]
    elif isinstance(request, FindHarvests):
        result = _find_harvests(db, request.arguments)
    elif isinstance(request, GetCustomerReceivable):
        result = report.customer_receivable(db, request.arguments.customer_id)
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    elif isinstance(request, GetWorkerPayable):
        result = report.worker_payable(db, request.arguments.worker_id)
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Worker not found")
    elif isinstance(request, GetSeasonSummary):
        result = report.season_summary(db, request.arguments.season_id)
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Season not found")
    elif isinstance(request, GetBusinessOverview):
        result = report.overview(db)
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unsupported query")
    return QueryResult(action=request.action, result=result)
