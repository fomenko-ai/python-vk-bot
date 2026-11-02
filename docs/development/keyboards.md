# Keyboards and buttons

Import `Keyboard`, `TextButton`, `CallbackButton`, `ButtonColor` and `ButtonType`
from `python_vk_bot` (also exported by `python_vk_bot.models`). These are public
alpha APIs: breaking changes may occur before 1.0 and are documented in the changelog;
cross-minor source compatibility is not guaranteed.

```python
from python_vk_bot import ButtonColor, CallbackButton, Keyboard, TextButton

ordinary = Keyboard(buttons=[[TextButton(label="Help", payload={"action": "help"})]])
inline = Keyboard(
    inline=True,
    buttons=[
        [
            CallbackButton(
                label="Confirm", payload={"action": "confirm"}, color=ButtonColor.POSITIVE
            ),
            CallbackButton(
                label="Cancel", payload={"action": "cancel"}, color=ButtonColor.NEGATIVE
            ),
        ]
    ],
)
```

Pass a keyboard to `Bot.send_message(..., keyboard=...)` or
`Bot.edit_message(..., keyboard=...)`. Each inner list is one row.
`Keyboard.inline` controls placement and defaults to `False`.
`one_time` defaults to `False` and only applies to ordinary keyboards.
`Keyboard(buttons=[])` removes the ordinary keyboard.

Text buttons send the label as a message with an optional payload and use
`MessageHandler`. Callback buttons emit `message_event` and use `MessageEventHandler`.
The button class determines the action type, independently of keyboard placement.
See [the runnable example](../../examples/keyboards.py) for acknowledgement and editing.

## Fields and enums

Both models require `label: str`. `payload` is optional; `color` defaults to
`ButtonColor.SECONDARY`. Unknown constructor fields are rejected, and assignment
to declared fields is validated. Nested mutable payload dictionaries are not frozen.
Labels and payloads are excluded from button reprs; serialized data is not redacted
and must not be logged indiscriminately.

`ButtonColor` is a `StrEnum` with `PRIMARY`, `SECONDARY`, `POSITIVE` and `NEGATIVE`.
`ButtonType` is a `StrEnum` with `TEXT` and `CALLBACK`. Their values are lowercase VK
strings. Use enum members in typed Python code; Pydantic can validate corresponding
strings in input data. `TextButton.type` is fixed to `ButtonType.TEXT`, and
`CallbackButton.type` to `ButtonType.CALLBACK`, including assignment validation.

Raw VK button dictionaries are also accepted inside `Keyboard.buttons`, including
mixed rows. They retain their structure and unknown JSON fields; their action
semantics are caller-controlled. Code inspecting an entry must distinguish
dictionaries from typed button instances. No local numeric label/payload/row limits
or complete VK keyboard validation are claimed.

## Payloads and serialization

`payload` accepts a JSON-compatible dictionary, a Pydantic `BaseModel`, an already
encoded JSON string, or `None`:

```python
from typing import Literal

from pydantic import BaseModel

from python_vk_bot import CallbackButton


class ActionPayload(BaseModel):
    action: Literal["confirm", "cancel"]


button = CallbackButton(label="Confirm", payload=ActionPayload(action="confirm"))
```

- Dictionaries are encoded once as compact JSON; non-finite numbers cannot be encoded.
- Models use their own `model_dump_json(by_alias=True)`, including their declared
  subclass fields and custom serialization. Their result must be suitable for VK.
- Strings are forwarded unchanged, without parsing or encoding them again. The caller
  is responsible for supplying valid JSON.
- `None` omits the action payload field.

`button.model_dump()` returns flat model fields. JSON mode (`model_dump(mode="json")`
or `model_dump_json()`) produces the VK shape with nested `action` and a sibling
`color`. This also works inside `Keyboard`; Bot uses its JSON serialization directly.
Default JSON serialization includes the action type and default color. Raw button
dictionaries must already contain VK's nested action and string payload.
JSON output validated back into `Keyboard` is represented by raw button dictionaries.

Outgoing payload models do not automatically validate incoming clicks. Use
`ActionPayload.model_validate_json(raw)` for a string or
`ActionPayload.model_validate(raw)` for an object, and handle `ValidationError`.
No automatic dispatch by payload model is provided.

## References and limits

Verified on 2026-11-02 against VK API 5.199. The official
[keyboard guide](https://dev.vk.com/ru/api/bots/development/keyboard) documents
`secondary`; the [VKCOM object schema](https://github.com/VKCOM/vk-api-schema/blob/master/messages/objects.json)
uses `default` instead. Typed colors follow the guide; no alias conversion is performed.
See [API verification](api-compatibility.md). Live delivery has not been tested for
these new models.
