from pathlib import Path

import pytest
from pydantic import Field, JsonValue, SecretStr, ValidationError
from pydantic_settings import SettingsConfigDict

from python_vk_bot import BotSettings, Update, filters
from python_vk_bot._config import TransportConfig
from python_vk_bot.errors import InvalidUpdateError
from python_vk_bot.models.api import LongPollResponse, LongPollServer

from .helpers import event, message


def test_environment_and_constructor_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VK_TOKEN", "synthetic-env-token")
    monkeypatch.setenv("VK_GROUP_ID", "42")
    monkeypatch.setenv("VK_TIMEOUT", "12.5")
    monkeypatch.setenv("VK_POLLING_WAIT", "30")
    settings = BotSettings(timeout=15.0)
    assert settings.token.get_secret_value() == "synthetic-env-token"
    assert settings.group_id == 42
    assert settings.timeout == 15.0
    assert settings.polling_wait == 30
    assert "synthetic-env-token" not in repr(settings)


def test_dotenv_is_explicit_and_environment_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "VK_TOKEN=synthetic-file-token\nVK_GROUP_ID=42\nVK_TIMEOUT=19\nUNRELATED=value\n"
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError):
        BotSettings()
    monkeypatch.setenv("VK_TIMEOUT", "20")
    settings = BotSettings(_env_file=dotenv)
    assert settings.timeout == 20.0
    assert settings.group_id == 42
    assert settings.token.get_secret_value() == "synthetic-file-token"


def test_settings_inheritance_alias_and_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    class ProjectSettings(BotSettings):
        model_config = SettingsConfigDict(env_prefix="PROJECT_")
        admin_ids: list[int] = Field(default_factory=list)
        debug: bool = False
        database_url: str = Field(validation_alias="TEST_DATABASE_URL")

    monkeypatch.setenv("PROJECT_TOKEN", "placeholder")
    monkeypatch.setenv("PROJECT_GROUP_ID", "42")
    monkeypatch.setenv("PROJECT_ADMIN_IDS", "[7, 8]")
    monkeypatch.setenv("PROJECT_DEBUG", "true")
    monkeypatch.setenv("TEST_DATABASE_URL", "sqlite:///example.db")
    settings = ProjectSettings()
    assert settings.admin_ids == [7, 8]
    assert settings.debug is True
    assert settings.database_url == "sqlite:///example.db"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("VK_GROUP_ID", "0"),
        ("VK_TOKEN", ""),
        ("VK_TIMEOUT", "0"),
        ("VK_TIMEOUT", "nan"),
        ("VK_TIMEOUT", "inf"),
        ("VK_API_VERSION", "invalid"),
        ("VK_POLLING_WAIT", "0"),
        ("VK_POLLING_WAIT", "91"),
    ],
)
def test_invalid_settings(name: str, value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VK_TOKEN", "placeholder")
    monkeypatch.setenv("VK_GROUP_ID", "42")
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        BotSettings()


def test_transport_configuration_ignores_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VK_TIMEOUT", "123")
    monkeypatch.setenv("VK_TOKEN", "synthetic-env-token")
    config = TransportConfig(token=SecretStr("explicit-token"))
    assert config.timeout == 40.0
    assert config.token.get_secret_value() == "explicit-token"
    with pytest.raises(ValidationError, match="frozen"):
        config.timeout = 1  # ty: ignore[invalid-assignment] -- exercise frozen-model rejection


def test_message_views_raw_fields_and_geo() -> None:
    raw_message = message()
    raw_message["geo"] = {"coordinates": {"latitude": 55.75, "longitude": 37.61}}
    raw_message["future_field"] = {"retained": True}
    payload = event()
    payload["object"] = {"message": raw_message, "client_info": {"keyboard": True}}
    payload["future_envelope"] = "retained"
    payload["secret"] = "synthetic-callback-secret"  # noqa: S105 -- synthetic test credential
    update = Update.from_dict(payload)
    assert update.message is not None
    assert update.message.geo is not None
    assert update.message.geo.coordinates.latitude == 55.75
    assert update.message.model_extra == {"future_field": {"retained": True}}
    assert update.object == payload["object"]
    assert update.model_extra == {"future_envelope": "retained"}
    assert "secret" not in update.model_dump()
    assert filters.LOCATION(update)
    assert (filters.TEXT & filters.Regex("ell"))(update)
    assert not (~filters.TEXT)(update)


@pytest.mark.parametrize("payload", ['{"action": "go"}', {"action": "go"}, None])
def test_message_event_preserves_payload_and_identifiers(payload: JsonValue) -> None:
    update = Update.from_dict(
        {
            "type": "message_event",
            "group_id": 42,
            "event_id": 123,
            "v": "5.199",
            "object": {"event_id": "button-event", "user_id": 7, "peer_id": 20, "payload": payload},
        }
    )
    assert update.event_id == "123"
    assert update.message_event is not None
    assert update.message_event.event_id == "button-event"
    assert update.message_event.payload == payload
    assert update.user_id == 7
    assert update.peer_id == 20
    assert update.message is None


def test_unknown_event_is_not_reclassified_as_a_message() -> None:
    payload = event()
    payload["type"] = "future_event"
    update = Update.from_dict(payload)
    assert update.object == payload["object"]
    assert update.message is None
    assert update.user_id is None
    assert update.peer_id is None
    assert (filters.LOCATION | filters.ALL)(update)


def test_invalid_event_error_does_not_include_payload() -> None:
    payload = event()
    payload["object"] = {"private": "private-event-content"}
    with pytest.raises(InvalidUpdateError) as captured:
        Update.from_dict(payload)
    assert "private-event-content" not in str(captured.value)


def test_poll_cursor_normalization_and_key_redaction() -> None:
    server = LongPollServer.model_validate(
        {"server": "https://poll.example/", "key": "synthetic-key", "ts": 12}
    )
    assert server.ts == "12"
    assert "synthetic-key" not in repr(server)
    assert LongPollResponse.model_validate({"failed": 1, "ts": 13}).ts == "13"
