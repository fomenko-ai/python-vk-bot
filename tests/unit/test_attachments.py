import copy

import pytest
from pydantic import JsonValue, ValidationError

from python_vk_bot import (
    Attachment,
    AudioMessageAttachment,
    DocumentAttachment,
    Message,
    PhotoAttachment,
    Update,
    VideoAttachment,
    filters,
)
from python_vk_bot.errors import InvalidUpdateError

from .helpers import event, message


@pytest.mark.parametrize(
    ("kind", "model", "identifier"),
    [
        ("photo", PhotoAttachment, "photo-42_11_access"),
        ("doc", DocumentAttachment, "doc-42_11_access"),
        ("video", VideoAttachment, "video-42_11_access"),
        ("audio_message", AudioMessageAttachment, "doc-42_11_access"),
    ],
)
def test_typed_views_preserve_raw_message_and_nested_unknown_fields(
    kind: str, model: type[Attachment], identifier: str
) -> None:
    raw = message()
    media: dict[str, JsonValue] = {
        "id": 11,
        "owner_id": -42,
        "access_key": "access",
        "future": {"nested": [1, None]},
    }
    raw["attachments"] = [{"type": kind, kind: media, "envelope_extra": "retained"}]
    untouched = copy.deepcopy(raw)
    parsed = Message.model_validate(raw)
    serialized = parsed.model_dump(mode="json")
    attachment = parsed.typed_attachments[0]
    assert isinstance(attachment, model)
    assert attachment.id == 11
    assert attachment.owner_id == -42
    assert attachment.to_attachment() == identifier
    assert attachment.media is not None
    assert attachment.media.access_key == "access"
    assert attachment.media.model_extra == {"future": {"nested": [1, None]}}
    assert attachment.model_extra == {"envelope_extra": "retained"}
    assert parsed.model_dump(mode="json") == serialized
    assert parsed.attachments == untouched["attachments"]
    assert raw == untouched
    assert "typed_attachments" not in serialized


@pytest.mark.parametrize(
    "attachment",
    [
        {"type": "future", "future": {"id": 1, "custom": [True]}},
        {"type": "photo", "photo": {"id": 1}},
        {"type": "photo", "photo": {"id": 0, "owner_id": 7}},
        {"type": "photo", "photo": {"id": True, "owner_id": 7}},
        {"type": "photo", "photo": {"id": 1, "owner_id": 0}},
        {"type": "doc", "doc": "malformed"},
        {"type": "audio_message", "audio_message": {"id": 1, "owner_id": 7, "duration": {}}},
        {"type": ["unknown"], "private": {"value": 1}},
        {"missing_type": True},
    ],
)
def test_incomplete_and_unknown_attachments_are_preserved(
    attachment: dict[str, JsonValue],
) -> None:
    raw = message()
    raw["attachments"] = [attachment]
    parsed = Message.model_validate(raw)
    view = parsed.typed_attachments[0]
    assert type(view) is Attachment
    assert view.model_dump(exclude_unset=True) == attachment
    assert view.id is None
    assert view.owner_id is None
    assert parsed.attachments == [attachment]
    with pytest.raises(ValueError, match="supported, complete"):
        view.to_attachment()


def test_typed_views_reflect_raw_edits_without_mutating_raw_data() -> None:
    raw = message()
    raw["attachments"] = [{"type": "photo", "photo": {"id": 11, "owner_id": 7}}]
    parsed = Message.model_validate(raw)
    first = parsed.typed_attachments[0]
    assert isinstance(first, PhotoAttachment)
    first.photo.id = 99
    assert parsed.typed_attachments[0].id == 11
    parsed.attachments[0]["photo"] = {"id": 12, "owner_id": 7}
    assert parsed.typed_attachments[0].to_attachment() == "photo7_12"
    assert first.id == 99


def test_photo_and_document_metadata_are_accessible() -> None:
    raw = message()
    raw["attachments"] = [
        {
            "type": "photo",
            "photo": {
                "id": 1,
                "owner_id": 7,
                "sizes": [
                    {"type": "x", "width": 100, "height": 80, "url": "https://media.example/"}
                ],
            },
        },
        {
            "type": "doc",
            "doc": {
                "id": 2,
                "owner_id": 7,
                "title": "report.pdf",
                "size": 100,
                "ext": "pdf",
                "type": 1,
            },
        },
    ]
    photo, document = Message.model_validate(raw).typed_attachments
    assert isinstance(photo, PhotoAttachment)
    assert photo.photo.sizes[0]["width"] == 100
    assert isinstance(document, DocumentAttachment)
    assert document.doc.title == "report.pdf"
    assert document.doc.size == 100
    with pytest.raises(ValidationError, match="frozen"):
        photo.type = "photo"  # ty: ignore[invalid-assignment] -- frozen public envelope


@pytest.mark.parametrize("geo", [None, {"coordinates": {"latitude": 0, "longitude": 0}}])
def test_location_absence_and_zero_coordinates(geo: JsonValue) -> None:
    raw_message = message()
    raw_message["geo"] = geo
    raw = event()
    raw["object"] = {"message": raw_message}
    update = Update.from_dict(raw)
    assert filters.LOCATION(update) is (geo is not None)
    assert update.message is not None
    if geo is not None:
        assert update.message.geo is not None
        assert update.message.geo.coordinates.latitude == 0
        assert update.message.geo.coordinates.longitude == 0


def test_location_retains_extra_fields_at_both_levels() -> None:
    raw = message()
    raw["geo"] = {
        "type": "point",
        "place": {"title": "place"},
        "coordinates": {"latitude": 55.75, "longitude": 37.61, "accuracy": 5},
    }
    parsed = Message.model_validate(raw)
    assert parsed.geo is not None
    assert parsed.geo.model_extra == {"type": "point", "place": {"title": "place"}}
    assert parsed.geo.coordinates.model_extra == {"accuracy": 5}


@pytest.mark.parametrize(
    "geo",
    [
        {},
        {"coordinates": None},
        {"coordinates": {}},
        {"coordinates": {"latitude": 55.75}},
        {"coordinates": {"longitude": 37.61}},
    ],
)
def test_incomplete_geo_fails_event_validation(geo: JsonValue) -> None:
    raw = event()
    raw_message = message()
    raw_message["geo"] = geo
    raw["object"] = {"message": raw_message}
    with pytest.raises(InvalidUpdateError):
        Update.from_dict(raw)


def test_location_filter_without_message_or_geo() -> None:
    assert not filters.LOCATION(Update.from_dict(event()))
    raw = event()
    raw["type"] = "future"
    raw["object"] = {}
    assert not filters.LOCATION(Update.from_dict(raw))
