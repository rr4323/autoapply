# `pydantic.TypeAdapter` — Validating a Bare List, Not a Model

## What it is

[01_pydantic_basics.md](01_pydantic_basics.md) covered `BaseModel.model_validate_json` — parsing+validating JSON into *one* model instance. `profiles.experience_json` (`TDD.md` §8) isn't one object, though — it's a bare JSON array of experience entries. `BaseModel` has no method for "validate this JSON as a list of models"; `TypeAdapter` is pydantic's tool for validating a type that isn't itself a `BaseModel` — a list, a dict, a union, or here, `list[ExperienceEntry]`.

## Verified example (from `backend/agents/src/agentos_agents/retriever/chunker.py`)

```python
from pydantic import BaseModel, TypeAdapter, ValidationError

class ExperienceEntry(BaseModel):
    id: str
    company: str
    title: str
    start_date: str
    end_date: str | None = None
    bullets: list[str] = []

_ExperienceList = TypeAdapter(list[ExperienceEntry])

def chunk_experience(experience_json: str | bytes) -> list[Chunk]:
    try:
        entries = _ExperienceList.validate_json(experience_json)
    except ValidationError as e:
        raise ChunkingError(f"experience_json does not match the expected shape: {e}") from e
    ...
```

**One call does both jobs** — `validate_json` parses the raw JSON *and* validates it against `list[ExperienceEntry]` in a single step, raising the same `ValidationError` whether the input is syntactically invalid JSON (`"{not valid json"`) or syntactically valid JSON with the wrong shape (a bare dict instead of a list, or a list entry missing `title`). `tests/test_chunker.py` has one test for each: `test_chunk_experience_rejects_invalid_json_syntax` and `test_chunk_experience_rejects_wrong_shape`/`..._missing_required_fields` — all three land in the same `except ValidationError` branch, verified by running them.

**Built once, module-level** — `TypeAdapter(list[ExperienceEntry])` does real work (building a validator from the type), so it's constructed once as `_ExperienceList` and reused across calls, not rebuilt inside `chunk_experience` on every invocation.

## Why this matters here specifically

`profiles.experience_json` is written by the **Go API** (`backend/api/internal/handlers/profile.go`'s `experienceEntry` struct), then read by **Python** chunking code — crossing the language boundary the same way the message envelope does ([00_README.md](00_README.md)'s "why Python starts later than Go" note). `ExperienceEntry` here is a second hand-copied mirror of that Go struct (same shape-must-match-by-hand tension as [09_strenum_field_types.md](09_strenum_field_types.md)'s `FieldType`/Go-enum pairing and `common/topics.py`) — but unlike a plain hand-rolled parser, a mismatch doesn't fail silently or crash with a raw `KeyError`; it raises a `ValidationError` naming exactly which field was missing or wrong-typed.

## Standard use case

Any time the JSON crossing a boundary is a list/array at the top level rather than a single object — a batch of records, a bare array API response — `TypeAdapter(list[Model])` is the direct tool, instead of wrapping the list in a throwaway single-field `BaseModel` just to get validation.
