from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, model_validator

from app.schemas.customer import CustomerCreate
from app.schemas.customer_payment import CustomerPaymentCreate
from app.schemas.expense import ExpenseCreate
from app.schemas.garden import GardenCreate
from app.schemas.grape_variety import GrapeVarietyCreate
from app.schemas.harvest import HarvestCreate
from app.schemas.labor_record import LaborRecordCreate
from app.schemas.sale import SaleCreate
from app.schemas.season import SeasonCreate
from app.schemas.worker import WorkerCreate
from app.schemas.worker_payment import WorkerPaymentCreate


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionEnvelope(StrictModel):
    confirmed: StrictBool | None = None


class HarvestArguments(HarvestCreate):
    model_config = ConfigDict(extra="forbid")


class SaleArguments(SaleCreate):
    model_config = ConfigDict(extra="forbid")


class CustomerPaymentArguments(CustomerPaymentCreate):
    model_config = ConfigDict(extra="forbid")


class LaborArguments(LaborRecordCreate):
    model_config = ConfigDict(extra="forbid")


class WorkerPaymentArguments(WorkerPaymentCreate):
    model_config = ConfigDict(extra="forbid")


class ExpenseArguments(ExpenseCreate):
    model_config = ConfigDict(extra="forbid")


class CustomerArguments(CustomerCreate):
    model_config = ConfigDict(extra="forbid")


class WorkerArguments(WorkerCreate):
    model_config = ConfigDict(extra="forbid")


class GardenArguments(GardenCreate):
    model_config = ConfigDict(extra="forbid")


class GrapeVarietyArguments(GrapeVarietyCreate):
    model_config = ConfigDict(extra="forbid")


class SeasonArguments(SeasonCreate):
    model_config = ConfigDict(extra="forbid")


class RecordHarvest(ActionEnvelope):
    action: Literal["record_harvest"]
    arguments: HarvestArguments


class RecordSale(ActionEnvelope):
    action: Literal["record_sale"]
    arguments: SaleArguments


class RecordCustomerPayment(ActionEnvelope):
    action: Literal["record_customer_payment"]
    arguments: CustomerPaymentArguments


class RecordLabor(ActionEnvelope):
    action: Literal["record_labor"]
    arguments: LaborArguments


class RecordWorkerPayment(ActionEnvelope):
    action: Literal["record_worker_payment"]
    arguments: WorkerPaymentArguments


class RecordExpense(ActionEnvelope):
    action: Literal["record_expense"]
    arguments: ExpenseArguments


class CreateCustomer(ActionEnvelope):
    action: Literal["create_customer"]
    arguments: CustomerArguments


class CreateWorker(ActionEnvelope):
    action: Literal["create_worker"]
    arguments: WorkerArguments


class CreateGarden(ActionEnvelope):
    action: Literal["create_garden"]
    arguments: GardenArguments


class CreateGrapeVariety(ActionEnvelope):
    action: Literal["create_grape_variety"]
    arguments: GrapeVarietyArguments


class CreateSeason(ActionEnvelope):
    action: Literal["create_season"]
    arguments: SeasonArguments


WriteAction = Annotated[
    RecordHarvest
    | RecordSale
    | RecordCustomerPayment
    | RecordLabor
    | RecordWorkerPayment
    | RecordExpense
    | CreateCustomer
    | CreateWorker
    | CreateGarden
    | CreateGrapeVariety
    | CreateSeason,
    Field(discriminator="action"),
]


class PendingActionPreview(BaseModel):
    action: str
    arguments: dict[str, Any]
    summary: str
    action_token: str
    calculated: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: Literal[True] = True


class ActionExecutionResult(BaseModel):
    action: str
    resource_type: str
    resource_id: int
    result: dict[str, Any]
    message: str


SearchName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class LookupArguments(StrictModel):
    name: SearchName | None = None


class IdArguments(StrictModel):
    customer_id: int = Field(gt=0)


class WorkerIdArguments(StrictModel):
    worker_id: int = Field(gt=0)


class SeasonIdArguments(StrictModel):
    season_id: int = Field(gt=0)


class EmptyArguments(StrictModel):
    pass


class HarvestLookupArguments(StrictModel):
    garden_id: int | None = Field(default=None, gt=0)
    season_id: int | None = Field(default=None, gt=0)
    harvest_date: date | None = None
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def check_date_range(self):
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("date_to must not be before date_from")
        return self


class HarvestLookupRead(BaseModel):
    harvest_id: int
    harvest_date: date
    quantity_kg: Decimal
    sold_quantity_kg: Decimal
    remaining_quantity_kg: Decimal
    season_id: int
    season_name: str | None
    garden_id: int
    garden_name: str
    variety_id: int
    variety_name: str


class FindGardens(StrictModel):
    action: Literal["find_gardens"]
    arguments: LookupArguments


class FindGrapeVarieties(StrictModel):
    action: Literal["find_grape_varieties"]
    arguments: LookupArguments


class FindSeasons(StrictModel):
    action: Literal["find_seasons"]
    arguments: LookupArguments


class FindCustomers(StrictModel):
    action: Literal["find_customers"]
    arguments: LookupArguments


class FindWorkers(StrictModel):
    action: Literal["find_workers"]
    arguments: LookupArguments


class FindHarvests(StrictModel):
    action: Literal["find_harvests"]
    arguments: HarvestLookupArguments


class GetCustomerReceivable(StrictModel):
    action: Literal["get_customer_receivable"]
    arguments: IdArguments


class GetWorkerPayable(StrictModel):
    action: Literal["get_worker_payable"]
    arguments: WorkerIdArguments


class GetSeasonSummary(StrictModel):
    action: Literal["get_season_summary"]
    arguments: SeasonIdArguments


class GetBusinessOverview(StrictModel):
    action: Literal["get_business_overview"]
    arguments: EmptyArguments


ReadAction = Annotated[
    FindGardens
    | FindGrapeVarieties
    | FindSeasons
    | FindCustomers
    | FindWorkers
    | FindHarvests
    | GetCustomerReceivable
    | GetWorkerPayable
    | GetSeasonSummary
    | GetBusinessOverview,
    Field(discriminator="action"),
]


class QueryResult(BaseModel):
    action: str
    result: Any
