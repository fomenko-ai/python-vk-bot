"""Donut event contracts and dispatch through the existing Callback pipeline."""

import httpx
import pytest
from pydantic import JsonValue, ValidationError

from python_vk_bot import (
    Application,
    Callback,
    Context,
    DonutSubscriptionEvent,
    DonutSubscriptionEventType,
    DonutSubscriptionHandler,
    Handler,
    MessageHandler,
    Update,
    filters,
)
from python_vk_bot.errors import CallbackAuthenticationError, InvalidUpdateError

from .helpers import event


def donut_payload(
    kind: str = "donut_subscription_create", *, event_id: str = "donut-1"
) -> dict[str, JsonValue]:
    return {
        "type": kind,
        "group_id": 42,
        "event_id": event_id,
        "v": "5.199",
        "object": {"user_id": 7},
    }


@pytest.mark.parametrize("kind", list(DonutSubscriptionEventType))
def test_typed_view_preserves_raw_data_and_identity(kind: DonutSubscriptionEventType) -> None:
    payload = donut_payload(kind)
    payload["object"] = {"user_id": 7, "amount": 0, "future": {"value": True}}
    payload["future_envelope"] = 12
    payload["event_id"] = 123
    update = Update.from_dict(payload)
    subscription = update.donut_subscription
    assert isinstance(subscription, DonutSubscriptionEvent)
    assert update.donut_subscription is subscription
    assert subscription.amount == 0
    assert subscription.amount_without_fee is None
    assert subscription.model_extra == {"future": {"value": True}}
    assert update.object == payload["object"]
    assert update.model_extra == {"future_envelope": 12}
    assert update.event_id == "123"
    assert update.user_id == 7
    assert update.group_id == 42
    assert update.peer_id is None
    assert update.message is None
    assert update.message_event is None


@pytest.mark.parametrize("user_id", [None, True, False, 0, -1, 7.0, 7.5, "7", "invalid"])
def test_invalid_user_id_is_rejected_without_exposing_payload(user_id: JsonValue) -> None:
    payload = donut_payload()
    payload["object"] = {"user_id": user_id, "private": "private-subscription-data"}
    with pytest.raises(InvalidUpdateError) as captured:
        Update.from_dict(payload)
    assert "private-subscription-data" not in str(captured.value)


@pytest.mark.parametrize("body", [{}, [], "invalid", None])
def test_invalid_donut_object(body: JsonValue) -> None:
    payload = donut_payload()
    payload["object"] = body
    with pytest.raises(InvalidUpdateError):
        Update.from_dict(payload)


def test_documented_money_fields_and_serialization() -> None:
    subscription = DonutSubscriptionEvent.model_validate(
        {
            "user_id": 7,
            "amount": 300,
            "amount_without_fee": 285.5,
            "amount_old": 200,
            "amount_new": 300,
            "amount_diff": 100,
            "amount_diff_without_fee": 95.25,
        }
    )
    assert subscription.amount == 300
    assert subscription.amount_without_fee == 285.5
    assert subscription.amount_old == 200
    assert subscription.amount_new == 300
    assert subscription.amount_diff == 100.0
    assert subscription.amount_diff_without_fee == 95.25
    assert (
        DonutSubscriptionEvent.model_validate_json(subscription.model_dump_json()) == subscription
    )
    assert DonutSubscriptionEvent(user_id=7, amount=None).amount is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", 1.5),
        ("amount_old", "200"),
        ("amount_new", True),
        ("amount_without_fee", "285"),
        ("amount_diff", False),
        ("amount_diff_without_fee", float("inf")),
        ("amount_diff", float("nan")),
    ],
)
def test_invalid_money_is_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        DonutSubscriptionEvent.model_validate({"user_id": 7, field: value})


@pytest.mark.parametrize(
    "kind", ["future_event", "donut_subscription.create", "donut_money_withdraw"]
)
def test_unknown_event_remains_raw(kind: str) -> None:
    update = Update.from_dict(donut_payload(kind))
    assert update.donut_subscription is None
    assert update.user_id is None
    assert not filters.DONUT_SUBSCRIPTION(update)
    assert update.object == {"user_id": 7}


@pytest.mark.parametrize(
    ("kind", "selected_filter"),
    [
        (DonutSubscriptionEventType.CREATE, filters.DONUT_SUBSCRIPTION_CREATE),
        (DonutSubscriptionEventType.PROLONGED, filters.DONUT_SUBSCRIPTION_PROLONGED),
        (DonutSubscriptionEventType.CANCELLED, filters.DONUT_SUBSCRIPTION_CANCELLED),
        (DonutSubscriptionEventType.EXPIRED, filters.DONUT_SUBSCRIPTION_EXPIRED),
        (DonutSubscriptionEventType.PRICE_CHANGED, filters.DONUT_SUBSCRIPTION_PRICE_CHANGED),
    ],
)
def test_filters_select_only_their_event(
    kind: DonutSubscriptionEventType, selected_filter: filters.Filter
) -> None:
    for candidate in DonutSubscriptionEventType:
        update = Update.from_dict(donut_payload(candidate))
        assert filters.DONUT_SUBSCRIPTION(update)
        assert selected_filter(update) is (candidate == kind)
        assert (~selected_filter)(update) is (candidate != kind)
        assert (selected_filter | filters.TEXT)(update) is (candidate == kind)
    message = Update.from_dict(event())
    assert message.donut_subscription is None
    assert not (selected_filter & filters.ALL)(message)


async def ignore(update: Update, context: Context) -> None:
    pass


def test_handler_selection_is_snapshotted_and_predicate_composes() -> None:
    selected: set[DonutSubscriptionEventType | str] = {DonutSubscriptionEventType.CREATE}
    handler = DonutSubscriptionHandler(ignore, event_types=selected)
    selected.add(DonutSubscriptionEventType.EXPIRED)
    create = Update.from_dict(donut_payload())
    expired = Update.from_dict(donut_payload(DonutSubscriptionEventType.EXPIRED))
    assert handler.check_update(create)
    assert not handler.check_update(expired)
    assert not handler.check_update(Update.from_dict(event()))
    assert not DonutSubscriptionHandler(ignore, event_types=[]).check_update(create)
    assert not DonutSubscriptionHandler(ignore, predicate=~filters.ALL).check_update(create)
    assert DonutSubscriptionHandler(ignore, event_types=[create.type]).check_update(create)
    with pytest.raises(ValueError, match="unknown"):
        DonutSubscriptionHandler(ignore, event_types=["unknown"])
    with pytest.raises(TypeError):
        DonutSubscriptionHandler(ignore, event_types=create.type)


async def test_dispatch_groups_user_context_and_internal_objects(application: Application) -> None:
    calls: list[str] = []
    contexts: list[Context] = []

    async def on_donut(update: Update, context: Context) -> None:
        calls.append(update.type)
        contexts.append(context)
        context.user_data["last"] = update.type
        context.peer_data["temporary"] = True

    async def on_message(update: Update, context: Context) -> None:
        assert context.user_data["last"] == "donut_subscription_price_changed"
        assert "temporary" not in context.peer_data
        calls.append("message")

    async def later(update: Update, context: Context) -> None:
        calls.append("later")

    async def skipped(update: Update, context: Context) -> None:
        raise AssertionError("A second handler in the same group must not run")

    application.add_handler(DonutSubscriptionHandler(on_donut), group=-1)
    application.add_handler(MessageHandler(on_message), group=-1)
    application.add_handler(Handler(skipped, predicate=filters.DONUT_SUBSCRIPTION), group=-1)
    application.add_handler(Handler(later), group=1)
    async with application:
        for kind in DonutSubscriptionEventType:
            await application.process_update(Update.from_dict(donut_payload(kind, event_id=kind)))
        await application.process_update(Update.from_dict(event()))
        await application.process_update(object())
    assert calls == [item for kind in DonutSubscriptionEventType for item in (kind, "later")] + [
        "message",
        "later",
    ]
    assert all(context.user_data is application.user_data[7] for context in contexts)
    assert all(context.bot_data is application.bot_data for context in contexts)
    assert contexts[0].peer_data is not contexts[1].peer_data
    assert None not in application.peer_data


async def test_callback_authentication_retry_and_deduplication(application: Application) -> None:
    calls = 0
    errors: list[Exception | None] = []

    async def on_donut(update: Update, context: Context) -> None:
        nonlocal calls
        calls += 1
        assert "secret" not in update.model_dump()
        if calls == 1:
            raise RuntimeError("synthetic failure")

    async def on_error(update: Update | None, context: Context) -> None:
        errors.append(context.error)

    application.add_handler(DonutSubscriptionHandler(on_donut))
    application.add_error_handler(on_error)
    callback = Callback(application, secret="synthetic", confirmation_code="confirmation")  # noqa: S106
    payload = {**donut_payload(), "secret": "synthetic"}
    async with application:
        for invalid in ({**payload, "secret": "wrong"}, {**payload, "group_id": 99}):
            with pytest.raises(CallbackAuthenticationError):
                await callback.handle(invalid)
        assert calls == 0
        with pytest.raises(RuntimeError, match="synthetic failure"):
            await callback.handle(payload)
        assert await callback.handle(payload) == "ok"
        assert await callback.handle(payload) == "ok"
    assert calls == 2
    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)


async def test_http_rejects_malformed_donut_and_accepts_valid_event(
    application: Application,
) -> None:
    pytest.importorskip("starlette")
    application.add_handler(DonutSubscriptionHandler(ignore))
    callback = Callback(application, secret="synthetic", confirmation_code="confirmation")  # noqa: S106
    app = callback.create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://callback.example"
        ) as receiver,
    ):
        payload = {**donut_payload(), "secret": "synthetic", "object": {"user_id": "7"}}
        response = await receiver.post("/callback", json=payload)
        assert response.status_code == 400
        payload["object"] = {"user_id": 7}
        response = await receiver.post("/callback", json=payload)
        assert response.status_code == 200
        assert response.text == "ok"
