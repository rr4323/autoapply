# `conftest.py` Is Also a Plain, Importable Module — `from conftest import X`, Not `from tests.conftest import X`

## What happened

Step 43 needed the exact same fixture-server/browser/fake-LLM setup `test_filler.py` (Step 41) already had. Following [python_concepts/13_conftest_and_pgvector_text_format.md](13_conftest_and_pgvector_text_format.md)'s established pattern, the obvious move was moving the shared pieces into `conftest.py`. Fixtures (`pg_pool`, `ats_fixtures_url`, `browser`) work automatically there, no import needed — that part was already known. But `conftest.py` also held plain values this time (`VALUES`, `CORRECT_FIELD_MAP`, the `FakeDomAnalysisLLMClient` class) that aren't fixtures, and *those* need an explicit import in any test file that uses them. The first attempt, `from tests.conftest import VALUES`, failed:

```
ModuleNotFoundError: No module named 'tests'
```

## Why

`backend/agents/tests/` has no `__init__.py` — it's not a Python package, just a directory pytest treats as a test root. With pytest's default "prepend" import mode, the directory containing each test file (here, `tests/`) gets inserted directly into `sys.path` — not its parent. That makes `conftest` importable as a **top-level module name**, exactly like any other file sitting in that directory would be, but there's no `tests` package for `tests.conftest` to resolve through.

```python
# tests/test_filler.py
from conftest import VALUES, FakeDomAnalysisLLMClient   # correct
from tests.conftest import VALUES, FakeDomAnalysisLLMClient  # ModuleNotFoundError
```

Verified: `uv run pytest tests/test_filler.py --collect-only` failed with the `tests.conftest` form and collected cleanly once changed to plain `conftest`.

## The general lesson

`conftest.py`'s two jobs — auto-discovered fixture provider, and ordinary importable module — follow different rules. Fixtures need zero imports anywhere. Everything else in the file (constants, helper classes, plain functions) needs an explicit `import`, and that import has to match how pytest actually put the directory on `sys.path`, not how the project's own package layout looks. When in doubt, `--collect-only` catches an import-path mistake immediately, before running any of the actual (slower, Docker-dependent) tests — worth reaching for first rather than debugging via a full test run.

## Standard use case

Any pytest project without `__init__.py` files under its test directory (the common case for a project that isn't also shipping its tests as an installable package) — shared non-fixture test helpers belong in `conftest.py` and get imported by bare module name from sibling test files.
