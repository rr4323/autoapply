"""Verifier Agent (docs/BACKEND_BUILD_STEPS.md Step 43) — the required
demo edge case: clean fixture -> submitted, CAPTCHA fixture ->
ready_for_review. Real Playwright against the real Step 39 fixtures;
POST /internal/agent/callback is respx-mocked to mirror TDD.md §7.2's
exact pre-submit rule (accepted iff not bot_check_detected) — Step 33
already adversarially proved the real Go endpoint enforces this
server-side; this test isolates what Step 42's bot-check detection
contributes to the outcome. Needs Docker, run via `make test-integration-py`.
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

import httpx
import pytest
import respx
from conftest import CORRECT_FIELD_MAP, VALUES, FakeDomAnalysisLLMClient

from agentos_agents.filler.browser import ephemeral_context
from agentos_agents.filler.fill import fill_form
from agentos_agents.filler.procedural_memory import ProceduralMemoryRepo
from agentos_agents.filler.verify import PolicyCallbackClient, verify_and_submit

pytestmark = pytest.mark.integration

POLICY_BASE_URL = "http://policy-engine.internal:8080"
CALLBACK_URL = f"{POLICY_BASE_URL}/internal/agent/callback"


def _mock_policy_engine() -> None:
    """Mirrors TDD.md §7.2's pre-submit rule for the one dimension this
    test varies: bot_check_detected. Score/velocity are held fixed at
    "clean" — those branches are Step 33's job to prove, not this one's.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["bot_check_detected"]:
            return httpx.Response(
                409,
                json={
                    "accepted": False,
                    "action": "require_review",
                    "reasons": ["bot-check detected"],
                },
            )
        return httpx.Response(
            200, json={"accepted": True, "action": "submit", "reasons": ["clean pass"]}
        )

    respx.post(CALLBACK_URL).mock(side_effect=responder)


@respx.mock
async def test_clean_fixture_results_in_submitted(pg_pool, browser, ats_fixtures_url):
    _mock_policy_engine()
    procedural_memory = ProceduralMemoryRepo(pg_pool)
    dom_llm = FakeDomAnalysisLLMClient()
    domain = urlparse(ats_fixtures_url).hostname

    async with ephemeral_context(browser, domain) as context:
        page = await context.new_page()
        await page.goto(f"{ats_fixtures_url}/clean/")
        await fill_form(page, domain, VALUES, procedural_memory, dom_llm)

        async with httpx.AsyncClient() as http_client:
            policy_client = PolicyCallbackClient(http_client, POLICY_BASE_URL, "s3cret")
            result = await verify_and_submit(page, "job-clean-1", domain, policy_client)

        submitted_marker = await page.locator("body").get_attribute("data-submitted")

    assert result.outcome == "submitted"
    assert result.bot_check_detected is False
    assert submitted_marker == "true"  # the submit button was actually clicked


@respx.mock
async def test_captcha_fixture_results_in_ready_for_review(pg_pool, browser, ats_fixtures_url):
    _mock_policy_engine()
    procedural_memory = ProceduralMemoryRepo(pg_pool)
    dom_llm = FakeDomAnalysisLLMClient()
    domain = urlparse(ats_fixtures_url).hostname

    async with ephemeral_context(browser, domain) as context:
        page = await context.new_page()
        await page.goto(f"{ats_fixtures_url}/captcha/")
        await fill_form(page, domain, VALUES, procedural_memory, dom_llm)

        async with httpx.AsyncClient() as http_client:
            policy_client = PolicyCallbackClient(http_client, POLICY_BASE_URL, "s3cret")
            result = await verify_and_submit(page, "job-captcha-1", domain, policy_client)

        submitted_marker = await page.locator("body").get_attribute("data-submitted")

    assert result.outcome == "ready_for_review"
    assert result.bot_check_detected is True
    assert submitted_marker is None  # submit was correctly withheld


def test_correct_field_map_is_reused_across_both_fixture_variants():
    # Sanity check that this test file's fixture assumptions (shared with
    # test_filler.py) still match both variants' real field ids.
    for name, selector in CORRECT_FIELD_MAP.items():
        assert selector.startswith("#")
        assert name in VALUES
