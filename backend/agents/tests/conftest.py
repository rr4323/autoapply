"""Shared fixtures for @pytest.mark.integration tests. Extracted here once
a second test file (test_indexer.py) needed the same Postgres testcontainer
setup as test_scraper_agent.py — same "duplicated setup drifts out of sync"
lesson as backend/api/internal/store/testmigrations.go's AllMigrationFiles,
applied at the same trigger point (the second occurrence, not preemptively).
"""

from __future__ import annotations

import json
from pathlib import Path

import asyncpg
import fakeredis
import pytest
from playwright.async_api import async_playwright
from testcontainers.community.nginx import NginxContainer
from testcontainers.community.postgres import PostgresContainer

from agentos_agents.common.llm_client import LLMClient

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "api" / "migrations"
# Mirrors backend/api/internal/store/testmigrations.go's AllMigrationFiles —
# Go and Python can't share that source file, so this list has to stay in
# sync by hand, same as common/topics.py.
MIGRATION_FILES = [
    "0001_users_profiles.up.sql",
    "0002_episodic_memory.up.sql",
    "0003_ingestion.up.sql",
    "0004_output_and_audit.up.sql",
    "0005_eval_and_mlops.up.sql",
    "0006_profile_fixes.up.sql",
    "0007_semantic_memory.up.sql",
]


@pytest.fixture
async def pg_pool():
    with PostgresContainer(
        "pgvector/pgvector:pg16", username="agentos", password="agentos_test", dbname="agentos_test"
    ) as container:
        dsn = container.get_connection_url(driver=None)
        pool = await asyncpg.create_pool(dsn)
        async with pool.acquire() as conn:
            for name in MIGRATION_FILES:
                await conn.execute((MIGRATIONS_DIR / name).read_text())
        yield pool
        await pool.close()


# fakeredis.FakeAsyncRedis — every agent-consumer test needs this identical
# fixture; long-duplicated across per-file definitions before landing here.
@pytest.fixture
def redis_client():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


# --- Shared across the Filler/Verifier test files (test_filler.py,
# test_verifier.py) — extracted here once the second file needed the
# exact same fixture-server/browser setup and fake DOM-analysis client. ---

ATS_FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "ats-fixtures"

# The real selectors in ats-fixtures/{clean,captcha}/index.html — a
# stand-in for what a real DOM-analysis LLM call would return, used so
# these tests are deterministic and need no network access.
CORRECT_FIELD_MAP = {
    "first_name": "#first_name",
    "last_name": "#last_name",
    "email": "#email",
    "phone": "#phone",
    "cover_letter": "#cover_letter",
    "q_why": "#q_why",
    "q_years": "#q_years",
    "q_auth": "#q_auth",
}

VALUES = {
    "first_name": "Jane",
    "last_name": "Doe",
    "email": "jane@example.com",
    "phone": "555-1234",
    "cover_letter": "I would love to join Acme Corp.",
    "q_why": "This role matches my backend experience.",
    "q_years": "5",
    "q_auth": "yes",
}


class FakeDomAnalysisLLMClient(LLMClient):
    def __init__(self) -> None:
        self.call_count = 0

    async def complete(self, system: str, user: str) -> str:
        self.call_count += 1
        return json.dumps(CORRECT_FIELD_MAP)


@pytest.fixture
def ats_fixtures_url():
    with NginxContainer("nginx:alpine").with_volume_mapping(
        str(ATS_FIXTURES_DIR), "/usr/share/nginx/html", mode="ro"
    ) as container:
        host_ip = container.get_container_host_ip()
        port = container.get_exposed_port(80)
        yield f"http://{host_ip}:{port}"


@pytest.fixture
async def browser():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        yield b
        await b.close()
