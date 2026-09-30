import json
import re
from typing import Any

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.ai.gemini_client import GeminiProvider, ToolCall
from app.schemas.assistant_actions import ReadAction, WriteAction
from app.schemas.assistant_chat import ChatRequest, ChatResponse, ChatResponseType
from app.services import assistant_actions
from app.services import action_tokens
from app.services import assistant_presentation
from app.services import assistant_execution


_WRITE_ADAPTER = TypeAdapter(WriteAction)
_READ_ADAPTER = TypeAdapter(ReadAction)
_WRITE_NAMES = frozenset(
    (
        "record_harvest", "record_sale", "record_customer_payment", "record_labor",
        "record_worker_payment", "record_expense", "create_customer", "create_worker",
        "create_garden", "create_grape_variety", "create_season",
    )
)
_READ_NAMES = frozenset(
    (
        "find_gardens", "find_grape_varieties", "find_seasons", "find_customers", "find_workers", "find_harvests",
        "get_customer_receivable", "get_worker_payable", "get_season_summary",
        "get_business_overview",
    )
)
_LOOKUP_NAMES = frozenset(("find_gardens", "find_grape_varieties", "find_seasons", "find_customers", "find_workers", "find_harvests"))
_CONFIRM_PHRASES = frozenset((
    "có", "dạ", "dạ có", "được", "được rồi", "ừ", "ừm", "ừ đúng",
    "ok", "oke", "okay", "đúng", "đúng rồi", "xác nhận", "ghi đi",
    "ghi lại đi", "lưu đi", "đồng ý",
))
_REJECT_PHRASES = frozenset(("không", "không nhé", "sai rồi", "thôi", "hủy", "bỏ đi", "không phải"))
_CREATE_PATTERN = re.compile(
    r"^(vẫn tạo|cứ tạo|tạo|thêm)\s+"
    r"(khách hàng|mối sỉ|khách|nhân công|người làm|vườn|giống nho|giống)\s+(.+)$",
    re.IGNORECASE,
)
_CREATE_ACTIONS = {
    "khách hàng": ("create_customer", "customer_name"),
    "mối sỉ": ("create_customer", "customer_name"),
    "khách": ("create_customer", "customer_name"),
    "nhân công": ("create_worker", "worker_name"),
    "người làm": ("create_worker", "worker_name"),
    "vườn": ("create_garden", "garden_name"),
    "giống nho": ("create_grape_variety", "variety_name"),
    "giống": ("create_grape_variety", "variety_name"),
}
_CREATE_LABELS = {
    "create_customer": "khách hàng",
    "create_worker": "nhân công",
    "create_garden": "vườn",
    "create_grape_variety": "giống nho",
}


def _intent(message: str) -> str:
    normalized = " ".join(message.casefold().strip(" \t\r\n.,!?;:…").split())
    if normalized in _REJECT_PHRASES:
        return "reject"
    if any(word in normalized for word in ("sửa", "đổi", "thay", "không phải", "sai")):
        return "correction"
    if normalized in _CONFIRM_PHRASES:
        return "confirm"
    return "other"


def _clarification(message: str, data: Any = None) -> ChatResponse:
    return ChatResponse(type=ChatResponseType.CLARIFICATION, message=message, data=data)


def _explicit_create(message: str) -> tuple[ToolCall, bool] | ChatResponse | None:
    cleaned = message.strip().rstrip(".!?").strip()
    match = _CREATE_PATTERN.fullmatch(cleaned)
    if match:
        verb, entity_type, name = match.groups()
        name = name.strip()
        if not name:
            return _clarification("Mẹ muốn đặt tên là gì ạ?")
        action, name_field = _CREATE_ACTIONS[entity_type.casefold()]
        return ToolCall(name=action, arguments={name_field: name}), verb.casefold() in ("vẫn tạo", "cứ tạo")
    if re.fullmatch(
        r"(?:vẫn tạo|cứ tạo|tạo|thêm)\s+(?:khách hàng|mối sỉ|khách|nhân công|người làm|vườn|giống nho|giống)",
        cleaned,
        flags=re.IGNORECASE,
    ):
        return _clarification("Mẹ muốn đặt tên là gì ạ?")
    generic = re.fullmatch(r"(?:tạo|thêm)\s+(.+)", cleaned, flags=re.IGNORECASE)
    if generic and generic.group(1)[0].isupper() and generic.group(1).split()[0].casefold() not in ("vụ", "mùa"):
        return _clarification("Mẹ muốn tạo người này là khách hàng hay nhân công? Nếu là vườn, mẹ nói 'tạo vườn' nhé.")
    return None


def _handle_call(db: Session, call: ToolCall, *, user_id: str, allow_duplicate: bool = False) -> tuple[ChatResponse | None, dict[str, Any] | None]:
    if call.name in _WRITE_NAMES:
        try:
            if call.name == "create_season" and not call.arguments.get("acquisition_type"):
                return _clarification("Mùa này là vườn nhà hay vườn mua quyền thu hoạch ạ?"), None
            request = _WRITE_ADAPTER.validate_python({"action": call.name, "arguments": call.arguments})
            if call.name in _CREATE_LABELS and not allow_duplicate:
                name_field = {
                    "create_customer": "customer_name",
                    "create_worker": "worker_name",
                    "create_garden": "garden_name",
                    "create_grape_variety": "variety_name",
                }[call.name]
                matches = assistant_actions.likely_entity_duplicates(
                    db, call.name, getattr(request.arguments, name_field)
                )
                if matches:
                    label = _CREATE_LABELS[call.name]
                    options = ", ".join(item["name"] for item in matches)
                    return _clarification(
                        f"Đã có {label} tên gần giống: {options}. Mẹ muốn dùng mục này hay vẫn tạo mới?",
                        matches,
                    ), None
            preview = assistant_actions.preview(db, request, user_id=user_id)
        except HTTPException as exc:
            if exc.status_code >= 500:
                raise
            return _clarification("Thông tin chưa đủ hoặc chưa hợp lệ. Mẹ kiểm tra lại giúp mình nhé."), None
        except ValidationError:
            return _clarification("Thông tin chưa đủ hoặc chưa hợp lệ. Mẹ kiểm tra lại giúp mình nhé."), None
        return ChatResponse(
            type=ChatResponseType.ACTION_PREVIEW,
            message=f"{preview.summary} Con ghi lại nhé?",
            pending_action=preview,
        ), None
    if call.name in _READ_NAMES:
        try:
            request = _READ_ADAPTER.validate_python({"action": call.name, "arguments": call.arguments})
            query_result = assistant_actions.query(db, request)
        except ValidationError:
            return _clarification("Mình cần thêm thông tin để tìm đúng mục. Mẹ nói rõ hơn nhé?"), None
        except HTTPException:
            return _clarification("Mình không tìm thấy mục này. Mẹ kiểm tra lại tên nhé?"), None
        result = query_result.model_dump(mode="json")["result"]
        if call.name in _LOOKUP_NAMES:
            if len(result) != 1:
                return _clarification(assistant_presentation.lookup_message(call.name, result), result), None
            return None, query_result.model_dump(mode="json")
        return ChatResponse(
            type=ChatResponseType.QUERY_RESULT,
            message=assistant_presentation.report_message(call.name, result),
            data=result,
        ), None
    return _clarification("Con chưa hỗ trợ yêu cầu đó. Mẹ nói lại theo cách khác nhé?"), None


def chat(db: Session, provider: GeminiProvider, request: ChatRequest, *, user_id: str) -> ChatResponse:
    history = [(item.role, item.message) for item in request.history]
    if request.pending_action is not None:
        intent = _intent(request.message)
        if intent == "confirm":
            try:
                pending = request.pending_action
                action = _WRITE_ADAPTER.validate_python(
                    {"action": pending.action, "arguments": pending.arguments, "confirmed": True}
                )
            except (ValidationError, HTTPException):
                return _clarification("Bản ghi này không còn hợp lệ. Mẹ kiểm tra và xem trước lại nhé?")
            if not action_tokens.token_matches(
                action, pending.action_token, user_id=user_id,
                idempotency_key=pending.idempotency_key, expires_at=pending.expires_at,
            ):
                return _clarification("Bản nháp đã bị thay đổi. Mẹ xem trước lại trước khi xác nhận nhé?")
            try:
                executed, duplicate = assistant_execution.execute_confirmed(
                    db, user_id=user_id, pending=pending, action=action
                )
            except (ValidationError, HTTPException):
                return _clarification("Bản ghi này không còn hợp lệ. Mẹ kiểm tra và xem trước lại nhé?")
            if executed is None:
                return ChatResponse(
                    type=ChatResponseType.MESSAGE,
                    message="Bản ghi này đang được xử lý. Mẹ thử lại sau nhé.",
                    pending_action=pending,
                )
            return ChatResponse(
                type=ChatResponseType.ACTION_EXECUTED,
                message=("Bản ghi này đã được lưu trước đó, con không ghi thêm lần nữa." if duplicate else executed.message),
                data=executed.model_dump(mode="json"),
            )
        if intent == "reject":
            return ChatResponse(type=ChatResponseType.MESSAGE, message="Đã bỏ bản ghi này, chưa lưu gì cả.")
        if intent != "correction":
            return ChatResponse(
                type=ChatResponseType.CLARIFICATION,
                message="Mẹ muốn xác nhận hay sửa lại bản ghi này?",
                pending_action=request.pending_action,
            )
        history.append(("assistant", f"Bản nháp chưa lưu: {request.pending_action.summary}. Đối số: {json.dumps(request.pending_action.arguments, ensure_ascii=False)}"))

    explicit_create = _explicit_create(request.message)
    if isinstance(explicit_create, ChatResponse):
        return explicit_create
    if explicit_create is not None:
        call, allow_duplicate = explicit_create
        response, _ = _handle_call(db, call, user_id=user_id, allow_duplicate=allow_duplicate)
        return response

    turn = provider.start(request.message, history)
    for _ in range(4):
        if not turn.calls:
            if not turn.text.strip():
                return _clarification("Mẹ nói rõ hơn giúp mình nhé?")
            public_text = assistant_presentation.safe_ai_message(turn.text)
            if public_text is None:
                return _clarification("Con chưa hiểu. Mẹ nói lại giúp con nhé?")
            response_type = ChatResponseType.CLARIFICATION if public_text.endswith("?") else ChatResponseType.MESSAGE
            return ChatResponse(type=response_type, message=public_text)
        if len(turn.calls) > 3 or (len(turn.calls) > 1 and any(call.name in _WRITE_NAMES for call in turn.calls)):
            return _clarification("Mẹ giúp con làm từng việc một nhé?")
        results = []
        for call in turn.calls:
            answer, feedback = _handle_call(db, call, user_id=user_id)
            if answer is not None:
                return answer
            results.append((call.name, feedback))
        turn = provider.continue_with_results(turn, results)
    return _clarification("Con vẫn chưa xác định được đúng mục. Mẹ cho con thêm tên hoặc chi tiết nhé?")
