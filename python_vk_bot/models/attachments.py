"""Typed VK attachment envelopes, retaining fields outside our supported subset."""

from typing import Literal, Union

from pydantic import Field, JsonValue, ValidationError, field_validator

from .base import VKModel


class Media(VKModel):
    id: int = Field(strict=True, gt=0)
    owner_id: int = Field(strict=True)
    access_key: Union[str, None] = Field(default=None, repr=False)

    @field_validator("owner_id")
    @classmethod
    def validate_owner(cls, value: int) -> int:
        if value == 0:
            raise ValueError("owner_id must be nonzero")
        return value


class Photo(Media):
    album_id: Union[int, None] = None
    date: Union[int, None] = None
    text: Union[str, None] = None
    sizes: list[dict[str, JsonValue]] = Field(default_factory=list)


class Document(Media):
    title: Union[str, None] = None
    size: Union[int, None] = None
    ext: Union[str, None] = None
    url: Union[str, None] = Field(default=None, repr=False)
    type: Union[int, None] = None


class Video(Media):
    title: Union[str, None] = None
    duration: Union[int, None] = None
    image: list[dict[str, JsonValue]] = Field(default_factory=list)


class AudioMessage(Media):
    duration: Union[int, None] = None
    waveform: list[int] = Field(default_factory=list)
    link_mp3: Union[str, None] = Field(default=None, repr=False)
    link_ogg: Union[str, None] = Field(default=None, repr=False)


class Attachment(VKModel, frozen=True):
    """Fallback envelope. Unknown or incomplete attachments cannot be resent implicitly."""

    type: JsonValue = None

    @property
    def media(self) -> Union[Media, None]:
        return None

    @property
    def id(self) -> Union[int, None]:
        return self.media.id if self.media is not None else None

    @property
    def owner_id(self) -> Union[int, None]:
        return self.media.owner_id if self.media is not None else None

    def to_attachment(self) -> str:
        """Return VK's wire identifier, including an access key when present."""
        media = self.media
        if media is None:
            raise ValueError("Only a supported, complete attachment can be sent")
        prefix = "doc" if self.type == "audio_message" else self.type
        identifier = f"{prefix}{media.owner_id}_{media.id}"
        return f"{identifier}_{media.access_key}" if media.access_key else identifier


class PhotoAttachment(Attachment):
    type: Literal["photo"] = "photo"
    photo: Photo

    @property
    def media(self) -> Photo:
        return self.photo


class DocumentAttachment(Attachment):
    type: Literal["doc"] = "doc"
    doc: Document

    @property
    def media(self) -> Document:
        return self.doc


class VideoAttachment(Attachment):
    type: Literal["video"] = "video"
    video: Video

    @property
    def media(self) -> Video:
        return self.video


class AudioMessageAttachment(Attachment):
    type: Literal["audio_message"] = "audio_message"
    audio_message: AudioMessage

    @property
    def media(self) -> AudioMessage:
        return self.audio_message


_ATTACHMENT_MODELS: dict[str, type[Attachment]] = {
    "photo": PhotoAttachment,
    "doc": DocumentAttachment,
    "video": VideoAttachment,
    "audio_message": AudioMessageAttachment,
}


def parse_attachment(value: dict[str, JsonValue]) -> Attachment:
    """Parse a view without making an otherwise valid Message fail validation."""
    kind = value.get("type")
    model = _ATTACHMENT_MODELS.get(kind) if isinstance(kind, str) else None
    if model is not None:
        try:
            return model.model_validate(value)
        except ValidationError:
            pass
    # The fallback also retains a missing or malformed type as its original JSON value.
    return Attachment.model_validate(value)


def serialize_attachment(value: Union[Union[str, Attachment], None]) -> Union[str, None]:
    return value.to_attachment() if isinstance(value, Attachment) else value
