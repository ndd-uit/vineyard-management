import inspect
import json
from pathlib import Path

from app.ai.gemini_client import SYSTEM_INSTRUCTION, _FIELD_DESCRIPTIONS, _TOOL_MODELS
from app.services import assistant_chat


def test_backend_has_no_phrase_specific_season_acquisition_router():
    assert not hasattr(assistant_chat, "_acquisition_from_message")
    assert not hasattr(assistant_chat, "_season_needs_acquisition")
    assert not hasattr(assistant_chat, "_season_needs_purchase_price")
    assert "season_acquisition" not in inspect.getsource(assistant_chat.chat)
    assert "season_acquisition" not in inspect.getsource(assistant_chat._handle_call)


def test_gemini_tools_explain_business_meaning():
    descriptions = {name: description for name, (_, description) in _TOOL_MODELS.items()}
    assert "gia đình" in descriptions["create_season"]
    assert "mua quyền" in descriptions["create_season"]
    assert "vườn người khác" in _FIELD_DESCRIPTIONS["acquisition_type"]
    assert "đây là vườn nhà" in _FIELD_DESCRIPTIONS["acquisition_type"]
    for action, concept in {
        "create_customer": "người mua nho",
        "create_worker": "người làm thuê",
        "record_sale": "bán nho",
        "record_customer_payment": "khách trả",
        "record_labor": "tiền công phát sinh",
        "record_worker_payment": "tiền đã trả",
        "record_expense": "không ghi tiền công",
        "record_harvest": "thu hoạch",
    }.items():
        assert concept in descriptions[action]
    assert "không hỏi lại" in SYSTEM_INSTRUCTION
    assert "bản xem trước" in SYSTEM_INSTRUCTION


def test_developer_evaluation_cases_are_structured_and_not_runtime_rules():
    path = Path(__file__).resolve().parents[1] / "evals" / "assistant_semantics.json"
    dataset = json.loads(path.read_text(encoding="utf-8"))
    assert "not training data" in dataset["purpose"]
    cases = dataset["cases"]
    assert len(cases) >= 20
    assert len({case["id"] for case in cases}) == len(cases)
    for case in cases:
        assert case["utterance"]
        assert "expected_action" in case
        assert isinstance(case["key_fields"], dict)
        assert isinstance(case["clarification_required"], bool)
        if case["clarification_required"]:
            assert case["clarification_reason"]
