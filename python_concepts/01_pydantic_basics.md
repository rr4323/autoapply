# Pydantic v2 Basics

## What it is

`pydantic.BaseModel` is a class that validates its own fields **automatically**, purely from type annotations — no separate `Validate()` method to write and remember to call, unlike Go's `encoding/json` (see [go_concepts/11_json_marshaling.md](../go_concepts/11_json_marshaling.md)). This is why Step 0 picked it specifically for anything crossing the message-bus boundary: at-least-once delivery (`TDD.md` §4) means a consumer will eventually see a malformed or redelivered message, and validation needs to happen automatically, not be something every agent remembers to check by hand.

## Verified example

```python
from pydantic import BaseModel, ValidationError


class Point(BaseModel):
    x: int
    y: int
    label: str


p = Point(x=1, y=2, label="origin")
print(p.model_dump_json())
```
```
{"x":1,"y":2,"label":"origin"}
```

Parsing JSON back into a model:
```python
json_str = '{"x": 5, "y": 6, "label": "roundtrip"}'
p2 = Point.model_validate_json(json_str)
print(p2)
```
```
x=5 y=6 label='roundtrip'
```

## The key contrast with Go: required fields are automatic

```python
Point(x=5, y=6)  # no "label" argument at all
```
```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Point
label
  Field required [type=missing, input_value={'x': 5, 'y': 6}, input_type=dict]
```
Any field **without a default value** is required — Pydantic raises `ValidationError` the instant you try to construct the model, before your code ever gets to use it. Go's `encoding/json` silently leaves a missing field at its zero value and requires you to write your own check; Pydantic makes "missing required field" impossible to accidentally skip.

## The two directions you'll use constantly

| Direction | Method |
|---|---|
| Model → JSON string | `model.model_dump_json()` |
| Model → plain dict | `model.model_dump()` |
| JSON string → Model (validates) | `Model.model_validate_json(json_str)` |
| dict → Model (validates) | `Model.model_validate(some_dict)` |

## Standard use case

The message envelope (`TDD.md` §4.1) is a `BaseModel` on the Python side: `job_id`, `trace_id`, `event_type`, `produced_by`, `timestamp`, `payload_ref` — every one required, so a consumer processing a Redis Streams message gets an automatic rejection (not a silent `None`/empty-string bug three steps later) the moment a malformed message is parsed. This is the Python half of `docs/BACKEND_BUILD_STEPS.md` Step 4's "reject missing `trace_id`/`job_id`" test requirement — it's close to free here, versus a hand-written `Validate()` on the Go side.
