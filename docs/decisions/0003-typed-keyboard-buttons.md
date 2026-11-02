# 0003: Separate typed keyboard buttons with JSON wire serialization

Status: accepted
Date: 2026-11-02
Task: typed-buttons

## Context

The user approved separate Pydantic button classes to remove nested action dictionaries
and manual payload encoding from application code, and requested enums for values.
PTB 22.8 provides the design reference for object buttons arranged in rows.

## Decision

Expose TextButton and CallbackButton with flat label, payload and color fields and
fixed Literal action types. Export ButtonColor and ButtonType as StrEnum values.
Keep shared implementation private. JSON-mode serialization builds VK action
envelopes and encodes dictionary/model payloads. Python-mode dumps remain flat.
Keep Keyboard in models/messages.py and add the models in models/keyboards.py.
Keyboard accepts typed instances and raw dictionaries; preserve unknown raw structures.
Bot keeps its serialization boundary. Incoming events and dispatch stay separate.

## Alternatives Considered

### One model selected by a type argument or factory methods

Fewer public classes, but ordinary constructors need an action selection and the
model is less suitable for future action kinds with different required fields.

### Typed action nested inside a typed button

Mirrors VK's schema directly, but retains extra nesting in user code.

## Consequences

### Positive

- Typed construction and enum completion without transport or dependency changes.
- Applications can use Pydantic models for their own payload data.
- Raw VK action structures remain available.

### Negative

- Python-mode and JSON-mode dumps deliberately have different shapes.
- Consumers inspecting Keyboard.buttons must narrow the model/dictionary union.
- Raw dictionaries bypass typed action validation; this is not full VK validation.

## Documentation

- [Keyboard API](../development/keyboards.md)
- [PTB reference](../architecture/python-telegram-bot-compatibility.md)
- [VK API support](../development/api-compatibility.md)
