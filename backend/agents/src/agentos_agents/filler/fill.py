"""Form filling (docs/BACKEND_BUILD_STEPS.md Step 41): checks procedural
memory (Step 40) for a known-good field_map first; falls back to
LLM-assisted DOM analysis on a cache miss or a stale map. Success/failure
is recorded back to procedural memory either way, so the next fill on
this domain benefits (or the map degrades toward "stale" if it keeps
failing) — the whole point of a learned "how" instead of re-analyzing
the same ATS layout on every single fill.

Scope: text-fillable fields (inputs, textareas, selects) — the actual
substance of "map generated content to form fields" (TDD.md's own
description of this agent). File-upload fields (a resume attachment) are
a materially different mechanism (a file path, not text content) and
aren't part of what this step tests.
"""

from __future__ import annotations

from dataclasses import dataclass

from playwright.async_api import Page

from agentos_agents.common.llm_client import LLMClient
from agentos_agents.filler.dom_analysis import infer_field_map
from agentos_agents.filler.procedural_memory import ProceduralMemoryRepo, is_stale


@dataclass
class FillResult:
    filled_fields: dict[str, str]
    field_map: dict[str, str]
    used_cache: bool


class FillError(Exception):
    """Raised when a field in the map doesn't resolve to a fillable element."""


async def fill_form(
    page: Page,
    ats_domain: str,
    values: dict[str, str],
    procedural_memory: ProceduralMemoryRepo,
    llm_client: LLMClient,
) -> FillResult:
    cached = await procedural_memory.get(ats_domain)
    used_cache = cached is not None and not is_stale(cached)

    if used_cache:
        field_map = cached.field_map  # type: ignore[union-attr]
    else:
        html = await page.content()
        field_map = await infer_field_map(llm_client, list(values.keys()), html)

    filled: dict[str, str] = {}
    try:
        for field_name, value in values.items():
            selector = field_map.get(field_name)
            if not selector:
                continue  # not every generated field has a matching form field
            await _fill_one(page, selector, value)
            filled[field_name] = value
    except Exception:
        if cached is not None:
            await procedural_memory.record_failure(ats_domain)
        raise

    await procedural_memory.record_success(ats_domain, field_map)
    return FillResult(filled_fields=filled, field_map=field_map, used_cache=used_cache)


async def _fill_one(page: Page, selector: str, value: str) -> None:
    locator = page.locator(selector)
    try:
        tag = await locator.evaluate("el => el.tagName.toLowerCase()")
    except Exception as e:
        raise FillError(f"selector {selector!r} did not resolve to an element: {e}") from e

    if tag == "select":
        await locator.select_option(value)
    else:
        await locator.fill(value)
