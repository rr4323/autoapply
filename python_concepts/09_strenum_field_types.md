# `enum.StrEnum` — a Closed Set of String Values

## What it is

[go_concepts/17_sqlc_codegen.md](../go_concepts/17_sqlc_codegen.md) covered Go's version of this idea: sqlc generates `type ApplicationStatus string` plus a `const` block of named values, one per Postgres enum label. Python's `enum.StrEnum` (3.11+, no external dependency) is the same shape — a fixed set of named string values, so `FieldType.NUMERIC` is both a real `str` (`"numeric"`, comparable/serializable directly) and a name `mypy`/`ruff` can check for typos, instead of a bare string that any part of the code could misspell silently.

## Verified example (from `backend/agents/src/agentos_agents/scraper/screener.py`)

```python
from enum import StrEnum

class FieldType(StrEnum):
    FREE_TEXT = "free_text"
    YES_NO = "yes_no"
    NUMERIC = "numeric"
    DATE = "date"
    ENUM = "enum"
```

Used directly in a dataclass field and compared/asserted like a plain string:
```python
@dataclass
class ScreenerQuestion:
    question: str
    field_type: FieldType
```
```python
>>> FieldType.NUMERIC == "numeric"
True
>>> [q.field_type for q in questions]
[<FieldType.FREE_TEXT: 'free_text'>, <FieldType.NUMERIC: 'numeric'>, <FieldType.YES_NO: 'yes_no'>]
```
Verified: `tests/test_screener.py` asserts `(question, field_type)` tuples straight against `FieldType.X` members — no `.value` unwrapping needed anywhere, because `StrEnum` members *are* strings at runtime.

## Why `StrEnum` and not `class FieldType(str, Enum)`

`ruff` (rule `UP042`) flagged the mixin form during this step:
```
UP042 Class FieldType inherits from both `str` and `enum.Enum`
help: Inherit from `enum.StrEnum`
```
Both work identically at runtime; `StrEnum` (added in 3.11, this project's floor per `pyproject.toml`'s `requires-python = ">=3.11"`) is the newer, more direct spelling of the same thing — one built-in base instead of two inherited ones.

## Go side, for contrast

Go has no built-in enum type at all — `ApplicationStatus` is just `string` underneath, and the `const` block is the *only* thing stopping a typo; nothing prevents constructing `ApplicationStatus("bogus")` directly. Python's `StrEnum` is stricter in one way (`FieldType("bogus")` raises `ValueError` at the boundary where untrusted data enters) and looser in another (nothing stops a call site from passing a raw `"numeric"` string instead of `FieldType.NUMERIC`, since they compare equal).

## Standard use case

Any closed set of string values that crosses a serialization boundary (JSON, a DB enum column, an API response) — one definition gives you comparison, iteration (`list(FieldType)`), and typo-safety in the same place.
