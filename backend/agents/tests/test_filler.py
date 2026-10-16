"""Filler Agent (docs/BACKEND_BUILD_STEPS.md Step 41): fresh ephemeral
browser context per fill (§14.3), egress restricted to the target domain,
fill from cached selectors with LLM-assisted DOM fallback on a miss.
Real Playwright + real Postgres (procedural memory) + the real Step 39
fixture forms — needs Docker, run via `make test-integration-py`.
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest
from conftest import VALUES, FakeDomAnalysisLLMClient

from agentos_agents.filler.browser import ephemeral_context
from agentos_agents.filler.fill import fill_form
from agentos_agents.filler.procedural_memory import ProceduralMemoryRepo

pytestmark = pytest.mark.integration


async def test_first_fill_uses_llm_fallback_second_fill_uses_cache(
    pg_pool, browser, ats_fixtures_url
):
    procedural_memory = ProceduralMemoryRepo(pg_pool)
    llm = FakeDomAnalysisLLMClient()
    domain = urlparse(ats_fixtures_url).hostname

    # First fill: no cached map for this domain yet.
    async with ephemeral_context(browser, domain) as context:
        page = await context.new_page()
        await page.goto(f"{ats_fixtures_url}/clean/")
        result1 = await fill_form(page, domain, VALUES, procedural_memory, llm)

    assert result1.used_cache is False
    assert llm.call_count == 1
    assert result1.filled_fields == VALUES

    # Second fill: a fresh context, but procedural memory now has a map.
    async with ephemeral_context(browser, domain) as context:
        page = await context.new_page()
        await page.goto(f"{ats_fixtures_url}/clean/")
        result2 = await fill_form(page, domain, VALUES, procedural_memory, llm)

    assert result2.used_cache is True
    assert llm.call_count == 1  # not called again — the cache was used
    assert result2.filled_fields == VALUES


async def test_fields_are_actually_filled_in_the_dom(pg_pool, browser, ats_fixtures_url):
    procedural_memory = ProceduralMemoryRepo(pg_pool)
    llm = FakeDomAnalysisLLMClient()
    domain = urlparse(ats_fixtures_url).hostname

    async with ephemeral_context(browser, domain) as context:
        page = await context.new_page()
        await page.goto(f"{ats_fixtures_url}/clean/")
        await fill_form(page, domain, VALUES, procedural_memory, llm)

        assert await page.locator("#first_name").input_value() == "Jane"
        assert await page.locator("#email").input_value() == "jane@example.com"
        assert await page.locator("#q_auth").input_value() == "yes"  # a <select>, not <input>


async def test_no_state_shared_between_two_consecutive_fills(pg_pool, browser, ats_fixtures_url):
    procedural_memory = ProceduralMemoryRepo(pg_pool)
    llm = FakeDomAnalysisLLMClient()
    domain = urlparse(ats_fixtures_url).hostname

    async with ephemeral_context(browser, domain) as context:
        page = await context.new_page()
        await page.goto(f"{ats_fixtures_url}/clean/")
        await page.evaluate("() => localStorage.setItem('leaked_marker', 'from_fill_one')")
        await fill_form(page, domain, VALUES, procedural_memory, llm)

    async with ephemeral_context(browser, domain) as context:
        page = await context.new_page()
        await page.goto(f"{ats_fixtures_url}/clean/")
        leaked = await page.evaluate("() => localStorage.getItem('leaked_marker')")

    assert leaked is None


async def test_egress_restricted_to_target_domain_blocks_third_party_requests(
    browser, ats_fixtures_url
):
    domain = urlparse(ats_fixtures_url).hostname
    failed_urls: list[str] = []

    async with ephemeral_context(browser, domain) as context:
        page = await context.new_page()
        page.on("requestfailed", lambda request: failed_urls.append(request.url))
        await page.goto(f"{ats_fixtures_url}/captcha/", wait_until="networkidle")

    assert any("google.com" in url for url in failed_urls)
