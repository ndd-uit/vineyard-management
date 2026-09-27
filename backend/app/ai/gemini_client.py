import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

from app.schemas.assistant_actions import (
    CustomerArguments,
    CustomerPaymentArguments,
    EmptyArguments,
    ExpenseArguments,
    GardenArguments,
    GrapeVarietyArguments,
    HarvestArguments,
    HarvestLookupArguments,
    IdArguments,
    LaborArguments,
    LookupArguments,
    SaleArguments,
    SeasonArguments,
    SeasonIdArguments,
    WorkerArguments,
    WorkerIdArguments,
    WorkerPaymentArguments,
)


SYSTEM_INSTRUCTION = (
    "Bạn là ddaij - trợ lý quản lý vườn nho cho mẹ. Hiểu tiếng Việt đời thường, từ đồng nghĩa và ngữ cảnh; "
    "trả lời ngắn gọn, tự nhiên. Chọn công cụ theo ý nghĩa nghiệp vụ, không theo một vài từ khóa cố định. "
    "Khi nói với mẹ, không hiện tên công cụ, mã số nội bộ, tên trường dữ liệu hay giá trị tiếng Anh như OWNED/ACTIVE; "
    "hãy nói 'vườn nhà mình', 'vườn mua quyền thu hoạch', 'đang chuẩn bị' bằng lời thường. "
    "Khách hàng là người mua nho, nhân công là người làm thuê. Bán nho khác khách trả nợ; "
    "ghi công lao động khác trả tiền công; chi phí không gồm tiền công. "
    "Thu hoạch là nho cắt được từ một mùa, chưa phải bán. Mùa vụ là một đợt trồng/thu hoạch của vườn. "
    "OWNED là vườn của gia đình, không có giá mua quyền; PURCHASED là mua quyền thu hoạch "
    "vườn người khác chỉ cho mùa này. Ví dụ 'đây là vườn nhà', 'vườn mình trồng', "
    "'vườn của nhà' là OWNED; 'mua quyền thu hoạch vườn này', "
    "'mua vườn này 30 triệu để cắt' là PURCHASED. Tên vườn 'Nhà' tự nó không xác định loại. "
    "Không bắt mẹ biết mã: dùng find_* để tìm thực thể đã có trước khi dùng ID; nhiều kết quả thì hỏi chọn, "
    "không có thì không bịa ID. Yêu cầu tạo mới rõ ràng dùng create_* thay vì báo không tìm thấy. "
    "Hỏi một câu ngắn khi thông tin thật sự thiếu hoặc mơ hồ; không hỏi lại điều mẹ đã nói rõ, "
    "không tự bịa tên, ngày, số ký, đơn vị tiền hay giá. "
    "Mọi công cụ ghi chỉ tạo bản xem trước; backend lưu sau khi mẹ xác nhận. "
    "Dùng kết quả báo cáo làm số liệu tài chính chính thức, không tự tính lại."
)


_TOOL_MODELS: dict[str, tuple[type[BaseModel], str]] = {
    "record_harvest": (HarvestArguments, "Xem trước nho vừa cắt/hái được trong một mùa; đây là thu hoạch, chưa phải bán nho."),
    "record_sale": (SaleArguments, "Xem trước giao/bán nho từ đợt thu hoạch cho khách mua; cần số ký và đơn giá, không phải ghi khách trả nợ."),
    "record_customer_payment": (CustomerPaymentArguments, "Xem trước tiền khách trả hoặc gửi trước; giảm công nợ chung, không gắn với một lần bán."),
    "record_labor": (LaborArguments, "Xem trước một lần nhân công làm việc và tiền công phát sinh trong mùa; chưa phải trả tiền cho họ."),
    "record_worker_payment": (WorkerPaymentArguments, "Xem trước tiền đã trả cho nhân công; giảm số còn phải trả, không gắn với một lần làm."),
    "record_expense": (ExpenseArguments, "Xem trước chi phí vật tư/vận chuyển/dụng cụ cho mùa; không ghi tiền công ở đây."),
    "create_customer": (CustomerArguments, "Xem trước tạo người mua nho/khách sỉ mới, không phải nhân công; chỉ khi người dùng muốn thêm mới."),
    "create_worker": (WorkerArguments, "Xem trước tạo người làm thuê/nhân công mới, không phải khách mua nho."),
    "create_garden": (GardenArguments, "Xem trước tạo vườn nho vật lý mới; không gán OWNED/PURCHASED cho vườn."),
    "create_grape_variety": (GrapeVarietyArguments, "Xem trước tạo giống nho mới khi người dùng yêu cầu."),
    "create_season": (SeasonArguments, "Xem trước mùa trồng/thu hoạch mới sau khi tìm đúng vườn và giống. OWNED là vườn gia đình không có giá mua quyền; PURCHASED là mua quyền cắt nho vườn người khác cho mùa này."),
    "find_gardens": (LookupArguments, "Tìm vườn đã có theo tên, trả mọi kết quả để chọn đúng mã; không tạo mới."),
    "find_grape_varieties": (LookupArguments, "Tìm giống nho đã có theo tên, trả mọi kết quả để chọn đúng mã; không tạo mới."),
    "find_seasons": (LookupArguments, "Tìm mùa vụ đã có theo tên trước khi xem báo cáo, ghi thu hoạch hay chi phí."),
    "find_customers": (LookupArguments, "Tìm người mua nho/khách sỉ đã có theo tên trước khi bán, nhận tiền hay xem công nợ."),
    "find_workers": (LookupArguments, "Tìm nhân công/người làm đã có theo tên trước khi ghi công, trả tiền hay xem còn phải trả."),
    "find_harvests": (HarvestLookupArguments, "Tìm đợt nho đã cắt theo vườn, mùa hoặc ngày trước khi bán; trả mọi đợt phù hợp, kể cả đã bán hết."),
    "get_customer_receivable": (IdArguments, "Lấy công nợ khách hàng đã được backend tính; nên tìm khách hàng trước."),
    "get_worker_payable": (WorkerIdArguments, "Lấy tiền công còn phải trả đã được backend tính; nên tìm nhân công trước."),
    "get_season_summary": (SeasonIdArguments, "Lấy tổng kết mùa vụ và lợi nhuận ước tính đã được backend tính; nên tìm mùa vụ trước."),
    "get_business_overview": (EmptyArguments, "Lấy tổng quan kinh doanh từ backend, không tự tính lại doanh thu hay lợi nhuận."),
}

_FIELD_DESCRIPTIONS = {
    "season_id": "Mã mùa vụ đã được xác nhận qua tìm kiếm.",
    "harvest_id": "Mã đợt thu hoạch do người dùng chọn; không được tự bịa.",
    "customer_id": "Mã khách hàng đã được xác nhận qua tìm kiếm.",
    "worker_id": "Mã nhân công đã được xác nhận qua tìm kiếm.",
    "harvest_date": "Ngày thu hoạch theo YYYY-MM-DD.",
    "date_from": "Ngày thu hoạch sớm nhất theo YYYY-MM-DD, bao gồm ngày này.",
    "date_to": "Ngày thu hoạch muộn nhất theo YYYY-MM-DD, bao gồm ngày này.",
    "sale_date": "Ngày bán theo YYYY-MM-DD.",
    "payment_date": "Ngày nhận hoặc trả tiền theo YYYY-MM-DD.",
    "work_date": "Ngày làm việc theo YYYY-MM-DD.",
    "expense_date": "Ngày phát sinh chi phí theo YYYY-MM-DD.",
    "quantity_kg": "Số ký nho, số thập phân dương.",
    "unit_price": "Giá một ký nho, số thập phân không âm bằng đồng.",
    "amount": "Số tiền bằng đồng, số thập phân dương.",
    "category": "Loại chi phí, không được là tiền công.",
    "work_type": "Công việc như cắt nho, làm cỏ, tỉa cành.",
    "name": "Một phần tên cần tìm; bỏ trống để xem tất cả.",
    "customer_name": "Tên khách hàng mua nho.",
    "worker_name": "Tên nhân công.",
    "garden_name": "Tên vườn nho.",
    "garden_id": "Mã vườn đã xác nhận qua tìm kiếm.",
    "variety_name": "Tên giống nho.",
    "variety_id": "Mã giống nho đã xác nhận qua tìm kiếm.",
    "season_name": "Tên mùa vụ tùy chọn.",
    "start_date": "Ngày bắt đầu mùa vụ theo YYYY-MM-DD, tùy chọn.",
    "end_date": "Ngày kết thúc mùa vụ theo YYYY-MM-DD, tùy chọn.",
    "acquisition_type": "OWNED: gia đình sở hữu vườn, ví dụ 'đây là vườn nhà', 'vườn mình trồng', 'vườn của nhà'. PURCHASED: mua quyền cắt nho vườn người khác cho mùa này, ví dụ 'mua quyền thu hoạch vườn này', 'mua vườn này 30 triệu để cắt'. Hỏi nếu thật sự chưa rõ.",
    "purchase_price": "Giá mua quyền thu hoạch bằng đồng khi PURCHASED; phải null khi OWNED, không tự đoán nếu chưa nêu.",
    "status": "Trạng thái mùa vụ: PLANNING, ACTIVE, HARVESTING hoặc COMPLETED.",
    "note": "Ghi chú tùy chọn.",
}


def _parameters_schema(model: type[BaseModel]) -> dict[str, Any]:
    source = model.model_json_schema()
    properties = {}
    for name, field in source.get("properties", {}).items():
        field_type = field.get("type")
        if "anyOf" in field:
            field_type = "string"
        properties[name] = {
            "type": field_type or "string",
            "description": _FIELD_DESCRIPTIONS.get(name, field.get("title", name)),
        }
    return {
        "type": "object",
        "properties": properties,
        "required": source.get("required", []),
        "additionalProperties": False,
    }


TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name=name,
            description=description,
            parameters_json_schema=_parameters_schema(model),
        )
        for name, (model, description) in _TOOL_MODELS.items()
    ]
)


class GeminiConfigurationError(Exception):
    pass


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class GeminiTurn:
    text: str
    calls: list[ToolCall]
    contents: list[types.Content] | None = None


class GeminiProvider:
    def __init__(self) -> None:
        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        api_key = os.getenv("GEMINI_API_KEY")
        model = os.getenv("GEMINI_MODEL")
        if not api_key or not model:
            raise GeminiConfigurationError("Gemini configuration is missing")
        self.model = model
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=20_000),
        )

    def _generate(self, contents: list[types.Content]) -> GeminiTurn:
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=f"{SYSTEM_INSTRUCTION} Hôm nay ở Việt Nam là {datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat()}.",
                tools=[TOOL],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        calls = [ToolCall(name=call.name, arguments=dict(call.args or {})) for call in (response.function_calls or [])]
        candidate = response.candidates[0].content if response.candidates else None
        if candidate is None:
            return GeminiTurn(text="", calls=calls, contents=contents)
        answer = " ".join(part.text for part in (candidate.parts or []) if part.text)
        return GeminiTurn(text=answer, calls=calls, contents=[*contents, candidate])

    def start(self, message: str, history: list[tuple[str, str]]) -> GeminiTurn:
        contents = [
            types.Content(role="model" if role == "assistant" else "user", parts=[types.Part.from_text(text=text)])
            for role, text in history
        ]
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
        return self._generate(contents)

    def continue_with_results(self, turn: GeminiTurn, results: list[tuple[str, dict[str, Any]]]) -> GeminiTurn:
        if turn.contents is None:
            raise RuntimeError("Gemini turn has no context")
        tool_content = types.Content(
            # The configured Gemini endpoint rejects role="tool" with HTTP 400.
            role="user",
            parts=[types.Part.from_function_response(name=name, response={"result": value}) for name, value in results],
        )
        return self._generate([*turn.contents, tool_content])


def get_gemini_provider() -> GeminiProvider:
    return GeminiProvider()


class LazyGeminiProvider:
    """Only construct the SDK client when a model turn is actually needed."""

    def __init__(self) -> None:
        self._provider: GeminiProvider | None = None

    def _get(self) -> GeminiProvider:
        if self._provider is None:
            self._provider = get_gemini_provider()
        return self._provider

    def start(self, message: str, history: list[tuple[str, str]]) -> GeminiTurn:
        return self._get().start(message, history)

    def continue_with_results(self, turn: GeminiTurn, results: list[tuple[str, dict[str, Any]]]) -> GeminiTurn:
        return self._get().continue_with_results(turn, results)
