"""Vietnamese text shown to the assistant's user; action data stays unchanged."""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import Customer, Garden, GrapeVariety, Season, Worker
from app.schemas.assistant_actions import (
    CreateCustomer,
    CreateGarden,
    CreateGrapeVariety,
    CreateSeason,
    CreateWorker,
    RecordCustomerPayment,
    RecordExpense,
    RecordHarvest,
    RecordLabor,
    RecordSale,
    RecordWorkerPayment,
    WriteAction,
)


_TECHNICAL_TEXT = re.compile(
    r"\b(?:OWNED|PURCHASED|ACTIVE|PLANNING|HARVESTING|COMPLETED|"
    r"(?:create|record|find|get)_[a-z_]+|[a-z_]+_id)\b|\bmã\s+\d+\b",
    re.IGNORECASE,
)
_HONORIFICS = ("cô", "chú", "anh", "chị", "bác", "ông", "bà")
_STATUS_TEXT = {
    "PLANNING": "Vụ này đang chuẩn bị.",
    "HARVESTING": "Vụ này đang thu hoạch.",
    "COMPLETED": "Vụ này đã kết thúc.",
}


def _number(value: Decimal | str | int) -> str:
    formatted = f"{Decimal(str(value)):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return formatted.rstrip("0").rstrip(",") if "," in formatted else formatted


def money(value: Decimal | str | int) -> str:
    return f"{_number(value)}đ"


def kilograms(value: Decimal | str | int) -> str:
    return f"{_number(value)} kg"


def day(value: date | str) -> str:
    actual = date.fromisoformat(value) if isinstance(value, str) else value
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    if actual == today:
        return "hôm nay"
    if actual == today - timedelta(days=1):
        return "hôm qua"
    return f"ngày {actual:%d/%m/%Y}"


def garden_name(name: str) -> str:
    clean = name.strip()
    return clean[0].lower() + clean[1:] if clean.casefold().startswith("vườn ") else f"vườn {clean}"


def season_name(name: str | None, garden: str | None = None) -> str:
    if name:
        clean = name.strip()
        if clean.casefold().startswith(("vụ ", "mùa ")):
            return clean[0].lower() + clean[1:]
        return f"vụ {clean}"
    return f"vụ ở {garden_name(garden)}" if garden else "vụ này"


def person_name(name: str) -> str:
    clean = name.strip()
    first = clean.split(maxsplit=1)[0].casefold()
    return clean[0].lower() + clean[1:] if first in _HONORIFICS else clean


def action_summary(db: Session, request: WriteAction, derived: dict[str, Any]) -> str:
    args = request.arguments
    if isinstance(request, RecordHarvest):
        season = db.get(Season, args.season_id)
        garden = db.get(Garden, season.garden_id)
        return f"{day(args.harvest_date).capitalize()}, {garden_name(garden.garden_name)} thu hoạch được {kilograms(args.quantity_kg)}."
    if isinstance(request, RecordSale):
        customer = db.get(Customer, args.customer_id)
        return (
            f"Mẹ bán cho {person_name(customer.customer_name)} {kilograms(args.quantity_kg)} {day(args.sale_date)}, "
            f"giá {money(args.unit_price)}/kg, tổng {money(derived['total_amount'])}."
        )
    if isinstance(request, RecordCustomerPayment):
        customer = db.get(Customer, args.customer_id)
        return f"{customer.customer_name} trả {money(args.amount)} {day(args.payment_date)}."
    if isinstance(request, RecordLabor):
        worker = db.get(Worker, args.worker_id)
        work = args.work_type.strip()
        return f"{worker.worker_name} {work[0].lower() + work[1:]} {day(args.work_date)}, tiền công {money(args.amount)}."
    if isinstance(request, RecordWorkerPayment):
        worker = db.get(Worker, args.worker_id)
        return f"Mẹ trả {person_name(worker.worker_name)} {money(args.amount)} tiền công {day(args.payment_date)}."
    if isinstance(request, RecordExpense):
        season = db.get(Season, args.season_id)
        garden = db.get(Garden, season.garden_id)
        return (
            f"Mẹ chi {money(args.amount)} cho {args.category.strip().casefold()} ở "
            f"{season_name(season.season_name, garden.garden_name)} {day(args.expense_date)}."
        )
    if isinstance(request, CreateCustomer):
        return f"Mẹ muốn thêm khách hàng {args.customer_name}."
    if isinstance(request, CreateWorker):
        return f"Mẹ muốn thêm nhân công {args.worker_name}."
    if isinstance(request, CreateGarden):
        return f"Mẹ muốn thêm {garden_name(args.garden_name)}."
    if isinstance(request, CreateGrapeVariety):
        return f"Mẹ muốn thêm giống nho {args.variety_name}."
    if isinstance(request, CreateSeason):
        garden = db.get(Garden, args.garden_id)
        variety = db.get(GrapeVariety, args.variety_id)
        sentences = [
            f"Mẹ muốn tạo {season_name(args.season_name)} cho {garden_name(garden.garden_name)}, "
            f"giống {variety.variety_name}."
        ]
        if args.acquisition_type.value == "OWNED":
            sentences.append("Đây là vườn nhà mình.")
        elif args.purchase_price is not None:
            sentences.append(f"Vườn này mình mua quyền thu hoạch với giá {money(args.purchase_price)}.")
        else:
            sentences.append("Vườn này mình mua quyền thu hoạch.")
        status_text = _STATUS_TEXT.get(args.status.value)
        if status_text:
            sentences.append(status_text)
        if args.start_date:
            sentences.append(f"Bắt đầu {day(args.start_date)}.")
        if args.end_date:
            sentences.append(f"Kết thúc {day(args.end_date)}.")
        return " ".join(sentences)
    raise ValueError("Unsupported write action")


def lookup_message(action: str, matches: list[dict[str, Any]]) -> str:
    if action == "find_harvests":
        if not matches:
            return "Con chưa tìm thấy đợt thu hoạch phù hợp. Mẹ cho con thêm tên vườn hoặc ngày nhé?"
        options = "; ".join(
            f"{day(item['harvest_date'])} ở {garden_name(item['garden_name'])}, "
            f"giống {item['variety_name']}, còn {kilograms(item['remaining_quantity_kg'])}"
            for item in matches
        )
        return f"Con thấy vài đợt thu hoạch: {options}. Mẹ muốn chọn đợt nào?"
    labels = {
        "find_gardens": ("vườn", "garden_name"),
        "find_grape_varieties": ("giống nho", "variety_name"),
        "find_seasons": ("mùa vụ", "season_name"),
        "find_customers": ("khách hàng", "customer_name"),
        "find_workers": ("nhân công", "worker_name"),
    }
    label, field = labels[action]
    if not matches:
        return f"Con chưa tìm thấy {label} phù hợp. Mẹ cho con thêm tên hoặc chi tiết nhé?"
    options = "; ".join(
        f"{item.get(field) or 'chưa có tên'}"
        + (f", số {item['phone']}" if item.get("phone") else "")
        + (f", {item['location_note']}" if item.get("location_note") else "")
        for item in matches
    )
    return f"Con thấy vài {label}: {options}. Mẹ muốn chọn mục nào?"


def report_message(action: str, result: dict[str, Any]) -> str:
    if action == "get_customer_receivable":
        return f"{result['customer_name']} còn nợ {money(result['outstanding_amount'])}."
    if action == "get_worker_payable":
        return f"Mình còn phải trả {person_name(result['worker_name'])} {money(result['outstanding_amount'])}."
    if action == "get_season_summary":
        label = season_name(result.get("season_name"), result.get("garden_name"))
        return (
            f"{label.capitalize()} có doanh thu {money(result['sales_revenue'])}, "
            f"chi phí {money(result['total_cost'])}, lãi ước tính {money(result['estimated_profit'])}."
        )
    return (
        f"Tổng doanh thu {money(result['total_sales_revenue'])}, "
        f"lãi ước tính {money(result['estimated_profit'])}."
    )


def safe_ai_message(message: str) -> str | None:
    """Avoid displaying raw internal fields if the model disregards its style instruction."""
    clean = message.strip()
    return None if _TECHNICAL_TEXT.search(clean) else clean
