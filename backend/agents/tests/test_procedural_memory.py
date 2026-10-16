"""docs/BACKEND_BUILD_STEPS.md Step 40: cache hit/miss/invalidate-on-failure
logic. is_stale is pure (plain unit tests, no Docker); the repo methods
touch real Postgres (@pytest.mark.integration, run via
`make test-integration-py`) — mirroring every other Postgres-backed
component in this project, not mocked DB calls.
"""

from __future__ import annotations

import pytest

from agentos_agents.filler.procedural_memory import (
    STALE_AFTER_FAILURES,
    ProceduralMemoryRepo,
    SelectorMap,
    is_stale,
)


def _map(failure_count: int) -> SelectorMap:
    return SelectorMap(
        ats_domain="boards.greenhouse.io",
        field_map={"first_name": "#first_name"},
        last_success_at=None,
        failure_count=failure_count,
    )


def test_is_stale_false_below_threshold():
    assert is_stale(_map(STALE_AFTER_FAILURES - 1)) is False


def test_is_stale_true_at_threshold():
    assert is_stale(_map(STALE_AFTER_FAILURES)) is True


def test_is_stale_true_above_threshold():
    assert is_stale(_map(STALE_AFTER_FAILURES + 1)) is True


def test_is_stale_false_with_no_failures():
    assert is_stale(_map(0)) is False


@pytest.mark.integration
async def test_cache_miss_returns_none(pg_pool):
    repo = ProceduralMemoryRepo(pg_pool)

    result = await repo.get("never-seen.example.com")

    assert result is None


@pytest.mark.integration
async def test_cache_hit_after_record_success(pg_pool):
    repo = ProceduralMemoryRepo(pg_pool)
    field_map = {"first_name": "#first_name", "email": "#email"}

    await repo.record_success("boards.greenhouse.io", field_map)
    result = await repo.get("boards.greenhouse.io")

    assert result is not None
    assert result.field_map == field_map
    assert result.failure_count == 0
    assert result.last_success_at is not None


@pytest.mark.integration
async def test_record_failure_increments_failure_count(pg_pool):
    repo = ProceduralMemoryRepo(pg_pool)
    await repo.record_success("jobs.lever.co", {"first_name": "#first_name"})

    await repo.record_failure("jobs.lever.co")
    once = await repo.get("jobs.lever.co")
    await repo.record_failure("jobs.lever.co")
    twice = await repo.get("jobs.lever.co")

    assert once.failure_count == 1
    assert twice.failure_count == 2


@pytest.mark.integration
async def test_map_becomes_stale_after_enough_recorded_failures(pg_pool):
    repo = ProceduralMemoryRepo(pg_pool)
    domain = "stale-test.example.com"
    await repo.record_success(domain, {"first_name": "#first_name"})

    for _ in range(STALE_AFTER_FAILURES):
        await repo.record_failure(domain)

    result = await repo.get(domain)
    assert is_stale(result) is True


@pytest.mark.integration
async def test_record_success_resets_failure_count_and_updates_map(pg_pool):
    repo = ProceduralMemoryRepo(pg_pool)
    domain = "recovery-test.example.com"
    await repo.record_success(domain, {"first_name": "#old_selector"})
    await repo.record_failure(domain)
    await repo.record_failure(domain)

    new_map = {"first_name": "#new_selector_found_by_llm_fallback"}
    await repo.record_success(domain, new_map)

    result = await repo.get(domain)
    assert result.failure_count == 0
    assert result.field_map == new_map


@pytest.mark.integration
async def test_record_failure_on_uncached_domain_is_a_safe_no_op(pg_pool):
    repo = ProceduralMemoryRepo(pg_pool)

    await repo.record_failure("no-such-domain.example.com")  # must not raise

    assert await repo.get("no-such-domain.example.com") is None
