"""M6 exit — the 3-scenario backend E2E against the full docker-compose
stack (docs/BACKEND_BUILD_STEPS.md Step 45, IMPLEMENTATION_PLAN.md §1):

1. Below-threshold JD -> no documents generated.
2. Clean ATS fixture, good score -> submitted.
3. CAPTCHA fixture, good score -> ready_for_review (the required edge case).

Needs `make up` already running — this test connects to the real compose
services over their host-mapped ports; it does not start them itself
(unlike every other integration test in this project, which spins its
own hermetic testcontainers). Run via `make test-e2e`.

Scoring is real end to end (Steps 27-30's actual formula, the real
Retriever/pgvector ranking), with only the deterministic demo LLM/
embedding clients (agentos_agents.demo_clients, wired into the running
agent-worker container because no ANTHROPIC_API_KEY/OPENAI_API_KEY is
configured) standing in for a real model call. The three scenarios are
engineered through real candidate-profile content, not through faking
the score directly — a below-threshold candidate genuinely has no
matching skills/experience for this JD, the same way a real one would.
"""

from __future__ import annotations

import asyncio
import json

import asyncpg
import httpx
import pytest

from agentos_agents.demo_clients import DemoEmbeddingClient
from agentos_agents.retriever.indexer import index_profile

pytestmark = pytest.mark.e2e

API_BASE_URL = "http://localhost:8080"
DATABASE_URL = "postgresql://agentos:agentos_dev@localhost:5432/agentos"
# Plain port 80 (nginx's real listening port *inside* the compose
# network) — not the 8082 host-mapped port. The E2E test process (on the
# host) never resolves or fetches this URL itself; it only passes the
# string through the API. The agent-worker container is what actually
# does the DNS lookup and fetch, from inside the compose network, where
# the "boards.greenhouse.io" alias (docker-compose.yml's ats-fixtures
# service) resolves to the fixture container — not the real internet
# Greenhouse.
JD_URL_CLEAN = "http://boards.greenhouse.io/clean/"
JD_URL_CAPTCHA = "http://boards.greenhouse.io/captcha/"
# One bullet per JD requirement (ats-fixtures/clean/index.html's three
# Requirements <li>s) rather than one blended paragraph — chunk_experience
# (Step 23) makes each bullet its own retrieval chunk, and the demo bag-
# of-words embedding's cosine similarity is diluted by *unrelated* terms
# sharing a chunk with the matching ones, so a tight per-requirement
# bullet scores retrieval much closer to a real semantic match than one
# bullet trying to cover all three at once would.
STRONG_PROFILE_BULLETS = [
    "5+ years of experience with Go in backend engineering roles.",
    "Deep experience designing and operating distributed systems.",
    "Built and ran production services backed by PostgreSQL and Redis.",
]
WEAK_PROFILE_BULLET = (
    "Experienced fashion retail manager skilled in visual merchandising, customer "
    "relations, and inventory software systems."
)

POLL_INTERVAL_SECONDS = 2
POLL_TIMEOUT_SECONDS = 90


async def wait_for_stack_ready() -> None:
    async with httpx.AsyncClient() as client:
        for _ in range(30):
            try:
                resp = await client.get(f"{API_BASE_URL}/readyz", timeout=2)
                if resp.status_code == 200:
                    return
            except httpx.RequestError:
                pass
            await asyncio.sleep(1)
    pytest.fail("API did not become ready — is `make up` running?")


async def seed_user_and_profile(
    pool: asyncpg.Pool, email: str, bullets: list[str], skills: list[str]
) -> str:
    user_id = await pool.fetchval(
        "INSERT INTO users (email) VALUES ($1) "
        "ON CONFLICT (email) DO UPDATE SET email = users.email "
        "RETURNING id",
        email,
    )
    experience = json.dumps(
        [
            {
                "id": "e1",
                "company": "Acme Corp",
                "title": "Engineer",
                "start_date": "2020-01",
                "end_date": None,
                "bullets": bullets,
            }
        ]
    )
    await pool.execute(
        "INSERT INTO profiles (user_id, skills, experience_json) VALUES ($1::uuid, $2, $3::jsonb) "
        "ON CONFLICT (user_id) DO UPDATE SET skills = EXCLUDED.skills, "
        "experience_json = EXCLUDED.experience_json",
        str(user_id),
        skills,
        experience,
    )
    await index_profile(pool, DemoEmbeddingClient(), str(user_id), experience)
    return str(user_id)


async def create_application(http_client: httpx.AsyncClient, user_id: str, jd_url: str) -> str:
    response = await http_client.post(
        f"{API_BASE_URL}/api/v1/applications",
        headers={"X-Demo-User-ID": user_id},
        json={"jd_url": jd_url},
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


async def poll_until_status(
    http_client: httpx.AsyncClient, user_id: str, app_id: str, terminal_statuses: set[str]
) -> str:
    deadline = asyncio.get_event_loop().time() + POLL_TIMEOUT_SECONDS
    last_status = ""
    while asyncio.get_event_loop().time() < deadline:
        response = await http_client.get(
            f"{API_BASE_URL}/api/v1/applications/{app_id}",
            headers={"X-Demo-User-ID": user_id},
        )
        assert response.status_code == 200, response.text
        last_status = response.json()["status"]
        if last_status in terminal_statuses:
            return last_status
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    pytest.fail(f"application {app_id} did not reach {terminal_statuses}, stuck at {last_status!r}")


@pytest.fixture
async def pg_pool_local():
    pool = await asyncpg.create_pool(DATABASE_URL)
    yield pool
    await pool.close()


async def test_below_threshold_produces_no_documents(pg_pool_local):
    await wait_for_stack_ready()
    user_id = await seed_user_and_profile(
        pg_pool_local,
        "e2e-below-threshold@example.com",
        [WEAK_PROFILE_BULLET],
        ["Retail Management"],
    )

    async with httpx.AsyncClient() as http_client:
        app_id = await create_application(http_client, user_id, JD_URL_CLEAN)
        status = await poll_until_status(
            http_client, user_id, app_id, {"below_threshold", "scored", "failed"}
        )

    assert status == "below_threshold"
    rows = await pg_pool_local.fetch(
        "SELECT id FROM generated_documents WHERE application_id = $1::uuid", app_id
    )
    assert rows == []


async def test_clean_fixture_results_in_submitted(pg_pool_local):
    await wait_for_stack_ready()
    user_id = await seed_user_and_profile(
        pg_pool_local,
        "e2e-clean@example.com",
        STRONG_PROFILE_BULLETS,
        ["Go", "distributed systems", "PostgreSQL", "Redis"],
    )

    async with httpx.AsyncClient() as http_client:
        app_id = await create_application(http_client, user_id, JD_URL_CLEAN)
        status = await poll_until_status(
            http_client, user_id, app_id, {"submitted", "ready_for_review", "failed"}
        )

    assert status == "submitted"


async def test_captcha_fixture_results_in_ready_for_review(pg_pool_local):
    await wait_for_stack_ready()
    user_id = await seed_user_and_profile(
        pg_pool_local,
        "e2e-captcha@example.com",
        STRONG_PROFILE_BULLETS,
        ["Go", "distributed systems", "PostgreSQL", "Redis"],
    )

    async with httpx.AsyncClient() as http_client:
        app_id = await create_application(http_client, user_id, JD_URL_CAPTCHA)
        status = await poll_until_status(
            http_client, user_id, app_id, {"submitted", "ready_for_review", "failed"}
        )

    assert status == "ready_for_review"
