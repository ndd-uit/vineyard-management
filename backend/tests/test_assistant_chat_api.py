from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from google.genai import types
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.ai import gemini_client
from app.ai.gemini_client import GeminiTurn, ToolCall
from app.database import Base, get_db
from app.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.models import (
    AssistantActionExecution,
    Customer,
    Expense,
    Garden,
    GrapeVariety,
    Harvest,
    Sale,
    Season,
    Worker,
)
from app.routers.assistant_chat import get_chat_provider
from app.services import action_tokens


class FakeProvider:
    def __init__(self, *turns):
        self.turns = list(turns)
        self.feedback = []
        self.history = None

    def start(self, message, history):
        self.history = history
        return self.turns.pop(0)

    def continue_with_results(self, turn, results):
        self.feedback.extend(results)
        return self.turns.pop(0)


def tool(tool_name, **arguments):
    return GeminiTurn(text="", calls=[ToolCall(name=tool_name, arguments=arguments)])


def say(message):
    return GeminiTurn(text=message, calls=[])


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("ASSISTANT_ACTION_SIGNING_KEY", "test-only-signing-key-at-least-32-bytes")
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(sub="test-user")
    try:
        with TestClient(app) as client:
            yield client, engine
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def use_provider(provider):
    app.dependency_overrides[get_chat_provider] = lambda: provider


def seed(engine):
    with Session(engine) as db:
        garden = Garden(garden_name="Vườn A")
        variety = GrapeVariety(variety_name="Nho A")
        customer = Customer(customer_name="Cô Lan")
        worker = Worker(worker_name="Chú Tâm")
        db.add_all([garden, variety, customer, worker])
        db.flush()
        season = Season(
            garden_id=garden.garden_id,
            variety_id=variety.variety_id,
            season_name="Mùa A",
            acquisition_type="OWNED",
            status="ACTIVE",
        )
        db.add(season)
        db.flush()
        harvest = Harvest(season_id=season.season_id, harvest_date=date(2026, 9, 1), quantity_kg=Decimal("100.00"))
        db.add(harvest)
        db.flush()
        ids = dict(season_id=season.season_id, harvest_id=harvest.harvest_id, customer_id=customer.customer_id, worker_id=worker.worker_id)
        db.commit()
        return ids


def count(engine, model):
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(model))


def chat(client, message, **extra):
    return client.post("/api/assistant/chat", json={"message": message, **extra})


def test_ordinary_message_and_simple_clarification(api):
    client, _ = api
    use_provider(FakeProvider(say("Chào mẹ, mẹ cần xem gì ạ?")))
    response = chat(client, "Chào con")
    assert response.status_code == 200
    assert response.json()["type"] == "CLARIFICATION"
    assert response.json()["message"] == "Chào mẹ, mẹ cần xem gì ạ?"
    use_provider(FakeProvider(say("Hôm nay vườn ổn ạ.")))
    assert chat(client, "Chào con").json()["type"] == "MESSAGE"


@pytest.mark.parametrize(
    ("lookup", "lookup_args", "report", "id_field", "question"),
    [
        ("find_customers", {"name": "Lan"}, "get_customer_receivable", "customer_id", "Cô Lan còn nợ bao nhiêu?"),
        ("find_workers", {"name": "Tâm"}, "get_worker_payable", "worker_id", "Còn nợ chú Tâm bao nhiêu?"),
        ("find_seasons", {"name": "Mùa A"}, "get_season_summary", "season_id", "Mùa A lời bao nhiêu?"),
    ],
)
def test_lookup_then_authoritative_report(api, lookup, lookup_args, report, id_field, question):
    client, engine = api
    ids = seed(engine)
    provider = FakeProvider(tool(lookup, **lookup_args), tool(report, **{id_field: ids[id_field]}))
    use_provider(provider)
    response = chat(client, question)
    assert response.status_code == 200
    assert response.json()["type"] == "QUERY_RESULT"
    assert response.json()["data"]
    assert len(provider.feedback) == 1
    assert provider.feedback[0][0] == lookup


def test_business_overview_uses_report_action(api):
    client, engine = api
    seed(engine)
    use_provider(FakeProvider(tool("get_business_overview")))
    response = chat(client, "Tổng quan vườn mình thế nào?")
    assert response.status_code == 200
    assert response.json()["type"] == "QUERY_RESULT"
    assert response.json()["data"]["total_harvest_kg"] == "100.00"


@pytest.mark.parametrize(
    ("action_name", "args", "model"),
    [
        ("record_harvest", {"season_id": "season_id", "harvest_date": "2026-09-02", "quantity_kg": "12.00"}, Harvest),
        ("record_sale", {"harvest_id": "harvest_id", "customer_id": "customer_id", "sale_date": "2026-09-02", "quantity_kg": "2.00", "unit_price": "80000.00"}, Sale),
        ("record_expense", {"season_id": "season_id", "expense_date": "2026-09-02", "category": "Phân bón", "amount": "700000.00"}, Expense),
    ],
)
def test_write_tool_only_previews(api, action_name, args, model):
    client, engine = api
    ids = seed(engine)
    values = {key: ids.get(value, value) for key, value in args.items()}
    before = count(engine, model)
    use_provider(FakeProvider(tool(action_name, **values)))
    response = chat(client, "Ghi giúp mẹ")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "ACTION_PREVIEW"
    assert body["pending_action"]["requires_confirmation"] is True
    assert body["pending_action"]["action"] == action_name
    assert count(engine, model) == before
    if action_name == "record_sale":
        assert body["pending_action"]["calculated"]["total_amount"] == "160000.00"


def test_explicit_confirmation_executes_once_without_model_call(api):
    client, engine = api
    ids = seed(engine)
    use_provider(FakeProvider(tool("record_harvest", season_id=ids["season_id"], harvest_date="2026-09-02", quantity_kg="12.00")))
    pending = chat(client, "Hôm nay hái thêm 12 ký").json()["pending_action"]
    use_provider(FakeProvider())
    response = chat(client, "xác nhận", pending_action=pending)
    assert response.status_code == 200
    assert response.json()["type"] == "ACTION_EXECUTED"
    assert response.json()["pending_action"] is None
    assert count(engine, Harvest) == 2


def test_rejection_and_non_confirmation_never_write(api):
    client, engine = api
    ids = seed(engine)
    use_provider(FakeProvider(tool("record_expense", season_id=ids["season_id"], expense_date="2026-09-02", category="Phân bón", amount="10.00")))
    pending = chat(client, "Mua phân").json()["pending_action"]
    use_provider(FakeProvider())
    assert chat(client, "không", pending_action=pending).json()["type"] == "MESSAGE"
    assert chat(client, "đúng nhưng để mai", pending_action=pending).json()["type"] == "CLARIFICATION"
    assert count(engine, Expense) == 0


def test_correction_repreviews_instead_of_executing_old_action(api):
    client, engine = api
    ids = seed(engine)
    use_provider(FakeProvider(tool("record_expense", season_id=ids["season_id"], expense_date="2026-09-02", category="Phân bón", amount="10.00")))
    pending = chat(client, "Mua phân 10 đồng").json()["pending_action"]
    provider = FakeProvider(tool("record_expense", season_id=ids["season_id"], expense_date="2026-09-02", category="Phân bón", amount="20.00"))
    use_provider(provider)
    response = chat(client, "Sửa lại thành 20 đồng", pending_action=pending)
    assert response.json()["type"] == "ACTION_PREVIEW"
    assert response.json()["pending_action"]["arguments"]["amount"] == "20.00"
    assert count(engine, Expense) == 0
    assert any("Bản nháp chưa lưu" in text for _, text in provider.history)


def test_no_pending_confirmation_cannot_execute(api):
    client, engine = api
    seed(engine)
    use_provider(FakeProvider(say("Mẹ muốn ghi việc gì ạ?")))
    response = chat(client, "ok")
    assert response.json()["type"] == "CLARIFICATION"
    assert count(engine, Expense) == 0


@pytest.mark.parametrize(("lookup", "name", "model", "name_field"), [
    ("find_workers", "Tâm", Worker, "worker_name"),
    ("find_customers", "Lan", Customer, "customer_name"),
])
def test_ambiguity_returns_options(api, lookup, name, model, name_field):
    client, engine = api
    seed(engine)
    with Session(engine) as db:
        db.add(model(**{name_field: f"Người khác {name}"}))
        db.commit()
    use_provider(FakeProvider(tool(lookup, name=name)))
    response = chat(client, f"Tìm {name}")
    assert response.json()["type"] == "CLARIFICATION"
    assert len(response.json()["data"]) == 2
    assert "mã" not in response.json()["message"].casefold()


def test_missing_lookup_does_not_invent_entity(api):
    client, engine = api
    seed(engine)
    use_provider(FakeProvider(tool("find_customers", name="Không có")))
    response = chat(client, "Tìm khách không có")
    assert response.json()["type"] == "CLARIFICATION"
    assert response.json()["data"] == []


def test_unknown_and_malformed_tools_cannot_write(api):
    client, engine = api
    seed(engine)
    use_provider(FakeProvider(tool("execute_arbitrary_python", command="danger")))
    assert chat(client, "Làm gì đó").json()["type"] == "CLARIFICATION"
    use_provider(FakeProvider(tool("record_expense", season_id=1, amount="10", confirmed=True)))
    assert chat(client, "Ghi chi phí").json()["type"] == "CLARIFICATION"
    assert count(engine, Expense) == 0


def test_provider_failure_does_not_leak_secrets(api):
    client, _ = api

    class BrokenProvider:
        def start(self, message, history):
            raise RuntimeError("private-api-key-and-db-url")

    use_provider(BrokenProvider())
    response = chat(client, "Chào")
    assert response.status_code == 503
    assert "private-api-key-and-db-url" not in response.text
    assert "Trợ lý" in response.text


def test_missing_configuration_returns_safe_error(api, monkeypatch):
    client, _ = api
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_MODEL", "")
    app.dependency_overrides.pop(get_chat_provider, None)
    response = chat(client, "Chào")
    assert response.status_code == 503
    assert "GEMINI_API_KEY" not in response.text


def test_confirmation_does_not_need_gemini_configuration(api, monkeypatch):
    client, engine = api
    ids = seed(engine)
    with Session(engine) as db:
        from app.schemas.assistant_actions import RecordHarvest, HarvestArguments
        from app.services.assistant_actions import preview

        pending = preview(db, RecordHarvest(
            action="record_harvest",
            arguments=HarvestArguments(
                season_id=ids["season_id"],
                harvest_date=date(2026, 9, 2),
                quantity_kg=Decimal("2.00"),
            ),
        ), user_id="test-user").model_dump(mode="json")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_MODEL", "")
    app.dependency_overrides.pop(get_chat_provider, None)
    response = chat(client, "ghi đi", pending_action=pending)
    assert response.status_code == 200
    assert response.json()["type"] == "ACTION_EXECUTED"
    assert count(engine, Harvest) == 2


def test_multi_turn_history_is_forwarded_to_provider(api):
    client, engine = api
    ids = seed(engine)
    provider = FakeProvider(tool("record_sale", harvest_id=ids["harvest_id"], customer_id=ids["customer_id"], sale_date="2026-09-02", quantity_kg="2.00", unit_price="80000.00"))
    use_provider(provider)
    response = chat(client, "Đợt sáng nay, 80 ngàn", history=[
        {"role": "user", "message": "Bán cô Lan 2 ký"},
        {"role": "assistant", "message": "Đợt nào và giá bao nhiêu một ký?"},
    ])
    assert response.json()["type"] == "ACTION_PREVIEW"
    assert len(provider.history) == 2
    assert count(engine, Sale) == 0


def test_google_sdk_uses_manual_tool_calling_without_network(monkeypatch):
    calls = []

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            calls.append((model, contents, config))
            if len(calls) == 1:
                function_call = types.FunctionCall(name="find_customers", args={"name": "Lan"})
                content = types.Content(role="model", parts=[types.Part(function_call=function_call)])
                return SimpleNamespace(function_calls=[function_call], candidates=[SimpleNamespace(content=content)])
            assert contents[-1].role == "user"
            content = types.Content(role="model", parts=[types.Part.from_text(text="Đã tìm thấy.")])
            return SimpleNamespace(function_calls=[], candidates=[SimpleNamespace(content=content)])

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")
    monkeypatch.setenv("GEMINI_MODEL", "fake-test-model")
    monkeypatch.setattr(gemini_client.genai, "Client", FakeClient)
    provider = gemini_client.GeminiProvider()
    first = provider.start("Tìm cô Lan", [])
    assert first.calls == [ToolCall(name="find_customers", arguments={"name": "Lan"})]
    second = provider.continue_with_results(first, [("find_customers", {"result": []})])
    assert second.text == "Đã tìm thấy."
    assert calls[0][0] == "fake-test-model"
    assert calls[0][2].automatic_function_calling.disable is True
    assert len(calls[0][2].tools[0].function_declarations) == 21
    assert "find_harvests" in {item.name for item in calls[0][2].tools[0].function_declarations}
    assert calls[1][1][-1].role == "user"


def find_harvests(client, **filters):
    return client.post(
        "/api/assistant/query",
        json={"action": "find_harvests", "arguments": filters},
    )


def test_find_harvests_filters_recent_order_and_remaining_quantity(api):
    client, engine = api
    ids = seed(engine)
    with Session(engine) as db:
        original = db.get(Harvest, ids["harvest_id"])
        older = Harvest(
            season_id=ids["season_id"],
            harvest_date=date(2026, 8, 31),
            quantity_kg=Decimal("20.00"),
        )
        newer = Harvest(
            season_id=ids["season_id"],
            harvest_date=date(2026, 9, 2),
            quantity_kg=Decimal("50.00"),
        )
        db.add_all([older, newer])
        db.flush()
        db.add_all([
            Sale(harvest_id=original.harvest_id, customer_id=ids["customer_id"], sale_date=date(2026, 9, 2), quantity_kg=Decimal("30.00"), unit_price=Decimal("2.00"), total_amount=Decimal("60.00")),
            Sale(harvest_id=original.harvest_id, customer_id=ids["customer_id"], sale_date=date(2026, 9, 3), quantity_kg=Decimal("20.00"), unit_price=Decimal("2.00"), total_amount=Decimal("40.00")),
            Sale(harvest_id=older.harvest_id, customer_id=ids["customer_id"], sale_date=date(2026, 9, 1), quantity_kg=Decimal("20.00"), unit_price=Decimal("2.00"), total_amount=Decimal("40.00")),
        ])
        season = db.get(Season, ids["season_id"])
        garden_id = season.garden_id
        older_id, newer_id = older.harvest_id, newer.harvest_id
        db.commit()

    response = find_harvests(client, season_id=ids["season_id"])
    assert response.status_code == 200
    rows = response.json()["result"]
    assert [row["harvest_id"] for row in rows] == [newer_id, ids["harvest_id"], older_id]
    original_row = rows[1]
    assert original_row["quantity_kg"] == "100.00"
    assert original_row["sold_quantity_kg"] == "50.00"
    assert original_row["remaining_quantity_kg"] == "50.00"
    assert original_row["season_name"] == "Mùa A"
    assert original_row["garden_name"] == "Vườn A"
    assert original_row["variety_name"] == "Nho A"
    assert rows[0]["sold_quantity_kg"] == "0.00"
    assert rows[2]["remaining_quantity_kg"] == "0.00"

    by_garden = find_harvests(client, garden_id=garden_id).json()["result"]
    assert len(by_garden) == 3
    exact = find_harvests(client, harvest_date="2026-09-01").json()["result"]
    assert [row["harvest_id"] for row in exact] == [ids["harvest_id"]]
    date_range = find_harvests(client, date_from="2026-09-01", date_to="2026-09-02").json()["result"]
    assert [row["harvest_id"] for row in date_range] == [newer_id, ids["harvest_id"]]
    assert find_harvests(client, harvest_date="2025-01-01").json()["result"] == []
    assert find_harvests(client, date_from="2026-09-02", date_to="2026-09-01").status_code == 422


def test_find_harvests_by_garden_excludes_other_gardens(api):
    client, engine = api
    ids = seed(engine)
    with Session(engine) as db:
        garden = Garden(garden_name="Vườn B")
        variety = GrapeVariety(variety_name="Nho B")
        db.add_all([garden, variety])
        db.flush()
        season = Season(garden_id=garden.garden_id, variety_id=variety.variety_id, season_name="Mùa B", acquisition_type="OWNED", status="ACTIVE")
        db.add(season)
        db.flush()
        other = Harvest(season_id=season.season_id, harvest_date=date(2026, 9, 3), quantity_kg=Decimal("25.00"))
        db.add(other)
        db.flush()
        other_garden_id, other_harvest_id = garden.garden_id, other.harvest_id
        db.commit()
    rows = find_harvests(client, garden_id=other_garden_id).json()["result"]
    assert [row["harvest_id"] for row in rows] == [other_harvest_id]
    assert ids["harvest_id"] not in [row["harvest_id"] for row in rows]


def test_chat_resolves_one_harvest_then_previews_sale(api):
    client, engine = api
    ids = seed(engine)
    provider = FakeProvider(
        tool("find_harvests", season_id=ids["season_id"], harvest_date="2026-09-01"),
        tool("record_sale", harvest_id=ids["harvest_id"], customer_id=ids["customer_id"], sale_date="2026-09-02", quantity_kg="2.00", unit_price="80000.00"),
    )
    use_provider(provider)
    response = chat(client, "Bán cô Lan 2 ký từ đợt cắt vườn A, giá 80 ngàn")
    assert response.status_code == 200
    assert response.json()["type"] == "ACTION_PREVIEW"
    assert response.json()["pending_action"]["arguments"]["harvest_id"] == ids["harvest_id"]
    assert provider.feedback[0][0] == "find_harvests"
    assert count(engine, Sale) == 0


def test_chat_ambiguous_or_missing_harvest_never_guesses(api):
    client, engine = api
    ids = seed(engine)
    with Session(engine) as db:
        db.add(Harvest(season_id=ids["season_id"], harvest_date=date(2026, 9, 1), quantity_kg=Decimal("15.00")))
        db.commit()
    use_provider(FakeProvider(tool("find_harvests", season_id=ids["season_id"], harvest_date="2026-09-01")))
    ambiguous = chat(client, "Đợt sáng nay")
    assert ambiguous.json()["type"] == "CLARIFICATION"
    assert len(ambiguous.json()["data"]) == 2
    assert "mã" not in ambiguous.json()["message"].casefold()
    use_provider(FakeProvider(tool("find_harvests", harvest_date="2025-01-01")))
    missing = chat(client, "Đợt năm ngoái")
    assert missing.json()["type"] == "CLARIFICATION"
    assert missing.json()["data"] == []
    assert count(engine, Sale) == 0


def test_action_token_blocks_duplicate_confirmation_and_tampering(api):
    client, engine = api
    ids = seed(engine)
    use_provider(FakeProvider(tool("record_expense", season_id=ids["season_id"], expense_date="2026-09-02", category="Phân bón", amount="10.00")))
    pending = chat(client, "Mua phân 10 đồng").json()["pending_action"]
    assert pending["action_token"].startswith("v1.")
    assert count(engine, Expense) == 0

    altered = {**pending, "arguments": {**pending["arguments"], "amount": "20.00"}}
    use_provider(FakeProvider())
    tampered = chat(client, "xác nhận", pending_action=altered)
    assert tampered.json()["type"] == "CLARIFICATION"
    assert "đã bị thay đổi" in tampered.json()["message"]
    altered_action = {
        **pending,
        "action": "record_harvest",
        "arguments": {
            "season_id": ids["season_id"],
            "harvest_date": "2026-09-02",
            "quantity_kg": "2.00",
        },
    }
    tampered_action = chat(client, "xác nhận", pending_action=altered_action)
    assert tampered_action.json()["type"] == "CLARIFICATION"
    assert "đã bị thay đổi" in tampered_action.json()["message"]
    assert count(engine, Expense) == 0
    assert count(engine, Harvest) == 1

    first = chat(client, "xác nhận", pending_action=pending)
    assert first.json()["type"] == "ACTION_EXECUTED"
    assert count(engine, Expense) == 1
    repeated = chat(client, "xác nhận", pending_action=pending)
    assert repeated.json()["type"] == "ACTION_EXECUTED"
    assert repeated.json()["data"] == first.json()["data"]
    assert "đã được lưu" in repeated.json()["message"]
    assert count(engine, Expense) == 1


def test_durable_replay_survives_new_client_and_returns_original_result(api):
    client, engine = api
    use_provider(FakeProvider())
    pending = chat(client, "Tạo vườn A").json()["pending_action"]
    first = chat(client, "có", pending_action=pending).json()
    with TestClient(app) as restarted_client:
        second = chat(restarted_client, "có", pending_action=pending).json()
    assert second["type"] == "ACTION_EXECUTED"
    assert second["data"] == first["data"]
    assert count(engine, Garden) == 1
    assert count(engine, AssistantActionExecution) == 1


def test_identical_new_previews_are_independently_executable(api):
    client, engine = api
    use_provider(FakeProvider())
    first = chat(client, "Tạo vườn A").json()["pending_action"]
    second = chat(client, "Tạo vườn A").json()["pending_action"]
    assert first["idempotency_key"] != second["idempotency_key"]
    assert first["action_token"] != second["action_token"]
    assert chat(client, "có", pending_action=first).json()["type"] == "ACTION_EXECUTED"
    assert chat(client, "có", pending_action=second).json()["type"] == "ACTION_EXECUTED"
    assert count(engine, Garden) == 2
    assert count(engine, AssistantActionExecution) == 2


def test_tampered_key_expiry_and_wrong_authenticated_user_are_rejected(api):
    client, engine = api
    use_provider(FakeProvider())
    pending = chat(client, "Tạo vườn A").json()["pending_action"]
    changed_key = {**pending, "idempotency_key": str(uuid4())}
    assert chat(client, "có", pending_action=changed_key).json()["type"] == "CLARIFICATION"
    expired = {**pending, "expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()}
    assert chat(client, "có", pending_action=expired).json()["type"] == "CLARIFICATION"
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(sub="other-user")
    assert chat(client, "có", pending_action=pending).json()["type"] == "CLARIFICATION"
    assert count(engine, Garden) == 0
    assert count(engine, AssistantActionExecution) == 0


def test_validly_signed_but_expired_preview_is_rejected(api):
    client, engine = api
    use_provider(FakeProvider())
    pending = chat(client, "Tạo vườn A").json()["pending_action"]
    from app.schemas.assistant_actions import CreateGarden, GardenArguments

    expired_at = datetime.now(UTC) - timedelta(seconds=1)
    action = CreateGarden(action="create_garden", arguments=GardenArguments(garden_name="A"))
    expired = {**pending, "expires_at": expired_at.isoformat(), "action_token": action_tokens.action_token(
        action, user_id="test-user", idempotency_key=UUID(pending["idempotency_key"]),
        expires_at=expired_at,
    )}
    assert chat(client, "có", pending_action=expired).json()["type"] == "CLARIFICATION"
    assert count(engine, Garden) == 0


def test_missing_signing_key_fails_closed(api, monkeypatch):
    client, engine = api
    use_provider(FakeProvider())
    monkeypatch.delenv("ASSISTANT_ACTION_SIGNING_KEY")
    assert chat(client, "Tạo vườn A").status_code == 503
    assert count(engine, Garden) == 0


def test_reused_key_with_different_signed_payload_is_conflict(api):
    client, engine = api
    use_provider(FakeProvider())
    pending = chat(client, "Tạo vườn A").json()["pending_action"]
    assert chat(client, "có", pending_action=pending).json()["type"] == "ACTION_EXECUTED"
    from app.schemas.assistant_actions import CreateGarden, GardenArguments

    altered_action = CreateGarden(action="create_garden", arguments=GardenArguments(garden_name="B"))
    altered = {
        **pending,
        "arguments": {"garden_name": "B"},
        "action_token": action_tokens.action_token(
            altered_action, user_id="test-user", idempotency_key=UUID(pending["idempotency_key"]),
            expires_at=datetime.fromisoformat(pending["expires_at"]),
        ),
    }
    assert chat(client, "có", pending_action=altered).json()["type"] == "CLARIFICATION"
    assert count(engine, Garden) == 1
    assert count(engine, AssistantActionExecution) == 1


def test_same_key_is_scoped_to_authenticated_user(api):
    client, engine = api
    use_provider(FakeProvider())
    first = chat(client, "Tạo vườn A").json()["pending_action"]
    assert chat(client, "có", pending_action=first).json()["type"] == "ACTION_EXECUTED"
    from app.schemas.assistant_actions import CreateGarden, GardenArguments

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(sub="other-user")
    action = CreateGarden(action="create_garden", arguments=GardenArguments(garden_name="A"))
    second = {**first, "action_token": action_tokens.action_token(
        action, user_id="other-user", idempotency_key=UUID(first["idempotency_key"]),
        expires_at=datetime.fromisoformat(first["expires_at"]),
    )}
    assert chat(client, "có", pending_action=second).json()["type"] == "ACTION_EXECUTED"
    assert count(engine, Garden) == 2
    assert count(engine, AssistantActionExecution) == 2


def test_business_failure_rolls_back_claim_and_allows_retry(api, monkeypatch):
    client, engine = api
    use_provider(FakeProvider())
    pending = chat(client, "Tạo vườn A").json()["pending_action"]
    from app.services import assistant_actions

    original = assistant_actions.execute_uncommitted

    def fail_after_flush(db, action):
        original(db, action)
        raise RuntimeError("simulated failure after business flush")

    monkeypatch.setattr(assistant_actions, "execute_uncommitted", fail_after_flush)
    assert chat(client, "có", pending_action=pending).status_code == 503
    assert count(engine, Garden) == 0
    assert count(engine, AssistantActionExecution) == 0
    monkeypatch.setattr(assistant_actions, "execute_uncommitted", original)
    assert chat(client, "có", pending_action=pending).json()["type"] == "ACTION_EXECUTED"
    assert count(engine, Garden) == 1


def test_validation_failure_rolls_back_claim(api):
    client, engine = api
    ids = seed(engine)
    use_provider(FakeProvider(tool(
        "record_sale", harvest_id=ids["harvest_id"], customer_id=ids["customer_id"],
        sale_date="2026-09-02", quantity_kg="10.00", unit_price="80000.00",
    )))
    pending = chat(client, "Bán 10 ký").json()["pending_action"]
    from app.models import Sale

    with Session(engine) as db:
        db.add(Sale(harvest_id=ids["harvest_id"], customer_id=ids["customer_id"],
                    sale_date=date(2026, 9, 2), quantity_kg=Decimal("95.00"),
                    unit_price=Decimal("80000.00"), total_amount=Decimal("7600000.00")))
        db.commit()
    assert chat(client, "có", pending_action=pending).json()["type"] == "CLARIFICATION"
    assert count(engine, AssistantActionExecution) == 0
    assert count(engine, Sale) == 1


def test_rejection_does_not_consume_action_token(api):
    client, engine = api
    ids = seed(engine)
    use_provider(FakeProvider(tool("record_harvest", season_id=ids["season_id"], harvest_date="2026-09-02", quantity_kg="2.00")))
    pending = chat(client, "Hái 2 ký").json()["pending_action"]
    use_provider(FakeProvider())
    assert chat(client, "không", pending_action=pending).json()["type"] == "MESSAGE"
    assert count(engine, Harvest) == 1
    confirmed = chat(client, "ghi đi", pending_action=pending)
    assert confirmed.json()["type"] == "ACTION_EXECUTED"
    assert count(engine, Harvest) == 2


def test_action_token_uses_normalized_decimal_arguments():
    from app.schemas.assistant_actions import ExpenseArguments, RecordExpense

    first = RecordExpense(action="record_expense", arguments=ExpenseArguments(
        season_id=1, expense_date=date(2026, 9, 2), category="Phân bón", amount=Decimal("10.0")
    ))
    second = RecordExpense(action="record_expense", arguments=ExpenseArguments(
        season_id=1, expense_date=date(2026, 9, 2), category="Phân bón", amount=Decimal("10.00")
    ))
    assert action_tokens.payload_hash(first) == action_tokens.payload_hash(second)


@pytest.mark.parametrize(
    ("message", "expected_action", "model"),
    [
        ("Tạo khách hàng Cô Lan", "create_customer", Customer),
        ("Thêm khách Cô Lan", "create_customer", Customer),
        ("Tạo mối sỉ Cô Lan", "create_customer", Customer),
        ("Tạo nhân công chú Tâm", "create_worker", Worker),
        ("Thêm người làm chú Tâm", "create_worker", Worker),
        ("Tạo vườn Nhà", "create_garden", Garden),
        ("Thêm vườn A", "create_garden", Garden),
    ],
)
def test_explicit_creation_previews_without_existing_lookup(api, message, expected_action, model):
    client, engine = api
    # Even a mistaken Gemini lookup must not hijack explicit create intent.
    provider = FakeProvider(tool("find_customers", name="Cô Lan"))
    use_provider(provider)
    response = chat(client, message)
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "ACTION_PREVIEW"
    assert body["pending_action"]["action"] == expected_action
    assert "không tìm thấy" not in body["message"].casefold()
    assert count(engine, model) == 0
    assert len(provider.turns) == 1


def test_ambiguous_creation_asks_entity_type_without_guessing(api):
    client, engine = api
    use_provider(FakeProvider())
    response = chat(client, "Tạo Cô Lan")
    assert response.status_code == 200
    assert response.json()["type"] == "CLARIFICATION"
    assert "khách hàng" in response.json()["message"]
    assert "nhân công" in response.json()["message"]
    assert count(engine, Customer) == 0
    assert count(engine, Worker) == 0


def test_explicit_create_requires_confirmation_and_creates_once(api):
    client, engine = api
    use_provider(FakeProvider())
    pending = chat(client, "Tạo khách hàng Cô Lan").json()["pending_action"]
    assert pending["action"] == "create_customer"
    assert count(engine, Customer) == 0
    assert chat(client, "không", pending_action=pending).json()["type"] == "MESSAGE"
    assert count(engine, Customer) == 0
    confirmed = chat(client, "xác nhận", pending_action=pending)
    assert confirmed.json()["type"] == "ACTION_EXECUTED"
    assert count(engine, Customer) == 1
    assert chat(client, "xác nhận", pending_action=pending).json()["type"] == "ACTION_EXECUTED"
    assert count(engine, Customer) == 1


def test_likely_duplicate_creation_clarifies_instead_of_saving(api):
    client, engine = api
    seed(engine)
    use_provider(FakeProvider())
    response = chat(client, "Tạo khách hàng Co Lan")
    assert response.status_code == 200
    assert response.json()["type"] == "CLARIFICATION"
    assert "Cô Lan" in response.json()["message"]
    assert len(response.json()["data"]) == 1
    assert count(engine, Customer) == 1


def test_explicit_override_of_duplicate_still_needs_preview_and_confirmation(api):
    client, engine = api
    seed(engine)
    use_provider(FakeProvider())
    response = chat(client, "Vẫn tạo khách hàng Cô Lan")
    assert response.json()["type"] == "ACTION_PREVIEW"
    assert count(engine, Customer) == 1
    assert chat(client, "xác nhận", pending_action=response.json()["pending_action"]).json()["type"] == "ACTION_EXECUTED"
    assert count(engine, Customer) == 2


def test_gemini_create_tool_also_checks_likely_duplicate(api):
    client, engine = api
    seed(engine)
    use_provider(FakeProvider(tool("create_worker", worker_name="Chú Tâm")))
    response = chat(client, "Ghi người làm này")
    assert response.json()["type"] == "CLARIFICATION"
    assert "Chú Tâm" in response.json()["message"]
    assert count(engine, Worker) == 1


@pytest.mark.parametrize("reply", [
    "có", "dạ", "dạ có", "được", "được rồi", "ừ", "ừm",
    "ok", "oke", "đúng", "đúng rồi", "xác nhận", "ghi đi", "lưu đi",
    "  CÓ!  ", " Dạ có. ", "ĐƯỢC RỒI?", "Ghi đi,",
])
def test_natural_vietnamese_confirmation_executes_pending_action(api, reply):
    client, engine = api
    use_provider(FakeProvider())
    pending = chat(client, "Tạo vườn A").json()["pending_action"]
    assert count(engine, Garden) == 0
    response = chat(client, reply, pending_action=pending)
    assert response.json()["type"] == "ACTION_EXECUTED"
    assert count(engine, Garden) == 1


@pytest.mark.parametrize("reply", [
    "có sửa lại...", "có nhưng...", "được, đổi thành...",
    "ừ nhưng sửa...", "sai rồi", "không", "sửa lại",
])
def test_mixed_correction_or_rejection_never_confirms(api, reply):
    client, engine = api
    use_provider(FakeProvider())
    pending = chat(client, "Tạo vườn A").json()["pending_action"]
    use_provider(FakeProvider(say("Mẹ muốn sửa thế nào?")))
    response = chat(client, reply, pending_action=pending)
    assert response.json()["type"] != "ACTION_EXECUTED"
    assert count(engine, Garden) == 0


def test_natural_confirmation_reuses_duplicate_token_protection(api):
    client, engine = api
    use_provider(FakeProvider())
    pending = chat(client, "Tạo vườn A").json()["pending_action"]
    assert chat(client, "không", pending_action=pending).json()["type"] == "MESSAGE"
    assert count(engine, Garden) == 0
    assert chat(client, "Có!", pending_action=pending).json()["type"] == "ACTION_EXECUTED"
    assert chat(client, "dạ có", pending_action=pending).json()["type"] == "ACTION_EXECUTED"
    assert count(engine, Garden) == 1


@pytest.mark.parametrize("message", ["Tạo giống Hồng Nhật", "Thêm giống Mẫu Đơn"])
def test_explicit_grape_variety_create_previews_without_gemini(api, message):
    client, engine = api
    provider = FakeProvider(tool("find_grape_varieties", name="không dùng"))
    use_provider(provider)
    preview = chat(client, message).json()
    assert preview["type"] == "ACTION_PREVIEW"
    assert preview["pending_action"]["action"] == "create_grape_variety"
    assert count(engine, GrapeVariety) == 0
    assert len(provider.turns) == 1
    assert chat(client, "có", pending_action=preview["pending_action"]).json()["type"] == "ACTION_EXECUTED"
    assert chat(client, "dạ có", pending_action=preview["pending_action"]).json()["type"] == "ACTION_EXECUTED"
    assert count(engine, GrapeVariety) == 1


def test_duplicate_grape_variety_asks_before_creation(api):
    client, engine = api
    with Session(engine) as db:
        db.add(GrapeVariety(variety_name="Hồng Nhật"))
        db.commit()
    use_provider(FakeProvider())
    response = chat(client, "Tạo giống Hong Nhat").json()
    assert response["type"] == "CLARIFICATION"
    assert "Hồng Nhật" in response["message"]
    assert count(engine, GrapeVariety) == 1


def test_season_chat_resolves_garden_and_variety_before_preview(api):
    client, engine = api
    seed(engine)
    with Session(engine) as db:
        garden_id = db.scalar(select(Garden.garden_id))
        variety_id = db.scalar(select(GrapeVariety.variety_id))
    provider = FakeProvider(
        tool("find_gardens", name="Vườn A"),
        tool("find_grape_varieties", name="Nho A"),
        tool("create_season", garden_id=garden_id, variety_id=variety_id, season_name="Vụ tháng 9",
             acquisition_type="PURCHASED", purchase_price="100.00", status="PLANNING"),
    )
    use_provider(provider)
    response = chat(client, "Tạo vụ tháng 9 cho vườn A, giống Nho A, mua quyền thu hoạch giá 100 đồng").json()
    assert response["type"] == "ACTION_PREVIEW"
    assert response["pending_action"]["action"] == "create_season"
    assert [name for name, _ in provider.feedback] == ["find_gardens", "find_grape_varieties"]
    assert count(engine, Season) == 1
    assert chat(client, "dạ có", pending_action=response["pending_action"]).json()["type"] == "ACTION_EXECUTED"
    assert chat(client, "có", pending_action=response["pending_action"]).json()["type"] == "ACTION_EXECUTED"
    assert count(engine, Season) == 2


@pytest.mark.parametrize("lookup, name, duplicate_model, duplicate_name", [
    ("find_gardens", "Vườn A", Garden, "Vườn AB"),
    ("find_grape_varieties", "Nho A", GrapeVariety, "Nho AA"),
])
def test_season_chat_ambiguous_reference_clarifies(api, lookup, name, duplicate_model, duplicate_name):
    client, engine = api
    seed(engine)
    with Session(engine) as db:
        db.add(duplicate_model(**{("garden_name" if duplicate_model is Garden else "variety_name"): duplicate_name}))
        db.commit()
    use_provider(FakeProvider(tool(lookup, name=name)))
    response = chat(client, "Tạo mùa mới cho vườn A, giống Nho A, mua quyền thu hoạch giá 100 đồng").json()
    assert response["type"] == "CLARIFICATION"
    assert len(response["data"]) == 2
    assert count(engine, Season) == 1


def test_season_chat_missing_acquisition_type_clarifies_without_guessing(api):
    client, engine = api
    seed(engine)
    provider = FakeProvider(tool("create_season", garden_id=1, variety_id=1, status="PLANNING"))
    use_provider(provider)
    response = chat(client, "Tạo vụ tháng 9 cho vườn Nhà, giống Hồng Nhật").json()
    assert response["type"] == "CLARIFICATION"
    assert "vườn nhà" in response["message"]
    assert "mua quyền" in response["message"]
    assert provider.turns == []
    assert count(engine, Season) == 1


def test_season_chat_missing_reference_does_not_invent_id(api):
    client, engine = api
    seed(engine)
    use_provider(FakeProvider(tool("find_grape_varieties", name="Giống không có")))
    response = chat(client, "Tạo mùa mới cho vườn A, giống không có, mua quyền thu hoạch giá 100 đồng").json()
    assert response["type"] == "CLARIFICATION"
    assert response["data"] == []
    assert count(engine, Season) == 1


def test_season_tool_missing_acquisition_type_asks_instead_of_preview(api):
    client, engine = api
    seed(engine)
    use_provider(FakeProvider(tool("create_season", garden_id=1, variety_id=1, status="PLANNING")))
    response = chat(client, "Ghi mùa vụ này").json()
    assert response["type"] == "CLARIFICATION"
    assert "vườn nhà" in response["message"]
    assert count(engine, Season) == 1


def test_gemini_owned_season_tool_previews_and_confirms(api):
    client, engine = api
    with Session(engine) as db:
        garden = Garden(garden_name="Nhà")
        variety = GrapeVariety(variety_name="Hồng Nhật")
        db.add_all([garden, variety])
        db.flush()
        garden_id, variety_id = garden.garden_id, variety.variety_id
        db.commit()
    provider = FakeProvider(
        tool("find_gardens", name="Nhà"),
        tool("find_grape_varieties", name="Hồng Nhật"),
        tool("create_season", garden_id=garden_id, variety_id=variety_id,
             acquisition_type="OWNED", status="PLANNING"),
    )
    use_provider(provider)
    response = chat(client, "Tạo vụ tháng 9 cho vườn Nhà, giống Hồng Nhật, đây là vườn nhà").json()
    assert response["type"] == "ACTION_PREVIEW"
    assert response["pending_action"]["arguments"]["acquisition_type"] == "OWNED"
    assert "purchase_price" not in response["pending_action"]["arguments"]
    assert count(engine, Season) == 0
    assert chat(client, "có", pending_action=response["pending_action"]).json()["type"] == "ACTION_EXECUTED"
    with Session(engine) as db:
        season = db.scalar(select(Season))
        assert season.acquisition_type.value == "OWNED"
        assert season.purchase_price is None


@pytest.mark.parametrize("phrase", [
    "vườn nhà mình", "vườn này nhà mình", "đợt này là nho nhà", "vườn của gia đình",
])
def test_gemini_interprets_varied_owned_phrases_through_structured_tool(api, phrase):
    client, engine = api
    seed(engine)
    use_provider(FakeProvider(tool("create_season", garden_id=1, variety_id=1,
                                   acquisition_type="OWNED", status="PLANNING")))
    response = chat(client, f"Tạo mùa mới cho vườn A, giống Nho A, {phrase}").json()
    assert response["type"] == "ACTION_PREVIEW"
    assert response["pending_action"]["arguments"]["acquisition_type"] == "OWNED"
    assert "purchase_price" not in response["pending_action"]["arguments"]
    assert count(engine, Season) == 1


@pytest.mark.parametrize("phrase", [
    "mua quyền thu hoạch vườn này", "mua vườn này 30 triệu để cắt", "vườn người ta, mình mua lại đợt này",
])
def test_gemini_interprets_varied_purchased_phrases_through_structured_tool(api, phrase):
    client, engine = api
    seed(engine)
    use_provider(FakeProvider(tool("create_season", garden_id=1, variety_id=1,
                                   acquisition_type="PURCHASED", status="PLANNING")))
    preview = chat(client, f"Tạo vụ mới cho vườn A, giống Nho A, {phrase}").json()
    assert preview["type"] == "ACTION_PREVIEW"
    assert preview["pending_action"]["arguments"]["acquisition_type"] == "PURCHASED"
    assert "purchase_price" not in preview["pending_action"]["arguments"]
    assert count(engine, Season) == 1


def test_owned_with_purchase_price_is_rejected_by_existing_season_validation(api):
    client, engine = api
    seed(engine)
    use_provider(FakeProvider(tool("create_season", garden_id=1, variety_id=1,
                                   acquisition_type="OWNED", purchase_price="250.00", status="PLANNING")))
    response = chat(client, "Tạo vụ mới cho vườn A, giống Nho A, đây là vườn nhà").json()
    assert response["type"] == "CLARIFICATION"
    assert count(engine, Season) == 1


def test_season_chat_preview_message_and_summary_hide_internal_values(api):
    client, engine = api
    seed(engine)
    use_provider(FakeProvider(tool("create_season", garden_id=1, variety_id=1,
                                   season_name="Vụ tháng 9", acquisition_type="OWNED", status="ACTIVE")))
    body = chat(client, "Tạo vụ tháng 9 cho vườn A, giống Nho A, vườn nhà mình").json()
    assert body["type"] == "ACTION_PREVIEW"
    assert "Con ghi lại nhé?" in body["message"]
    assert "vườn A" in body["message"]
    assert "Nho A" in body["message"]
    assert "vườn nhà mình" in body["message"]
    for public_text in (body["message"], body["pending_action"]["summary"]):
        assert all(term not in public_text for term in ("OWNED", "PURCHASED", "ACTIVE", "create_season", "garden_id", "variety_id"))
    assert body["pending_action"]["arguments"]["acquisition_type"] == "OWNED"
    assert count(engine, Season) == 1


def test_report_message_formats_money_for_mother(api):
    client, engine = api
    ids = seed(engine)
    use_provider(FakeProvider(tool("get_customer_receivable", customer_id=ids["customer_id"])))
    body = chat(client, "Cô Lan còn nợ bao nhiêu?").json()
    assert body["type"] == "QUERY_RESULT"
    assert "Cô Lan" in body["message"]
    assert "đ" in body["message"]
    assert "customer_id" not in body["message"]


def test_model_text_with_internal_terms_is_not_shown_to_mother(api):
    client, _ = api
    use_provider(FakeProvider(say("create_season garden_id=1 OWNED ACTIVE")))
    body = chat(client, "Tạo vụ mới").json()
    assert body["type"] == "CLARIFICATION"
    assert all(term not in body["message"] for term in ("create_season", "garden_id", "OWNED", "ACTIVE"))
