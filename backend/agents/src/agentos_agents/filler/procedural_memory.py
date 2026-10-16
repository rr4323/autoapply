"""Procedural memory: per-ATS-domain selector maps (docs/BACKEND_BUILD_STEPS.md
Step 40, TDD.md §5/§8). The Filler Agent (Step 41) checks this first for a
known-good field_map before falling back to LLM-assisted DOM analysis — a
domain filled successfully before shouldn't need a fresh analysis every
time. A failed fill increments failure_count rather than deleting the row
outright, so a map that's degraded but not yet unreliable still gets used;
is_stale draws the line for when to stop trusting it and fall back.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

import asyncpg

# How many recorded failures before a cached selector map is no longer
# trusted (the Filler Agent should fall back to LLM-assisted DOM analysis
# instead). A documented starting point, not a calibrated number — no
# fill-history data exists yet to derive one from, the same cold-start
# gap as every other threshold picked this way in this project (Step 27's
# combiner weights, Step 35's grounded-claim ratio).
STALE_AFTER_FAILURES = 2


@dataclass
class SelectorMap:
    ats_domain: str
    field_map: dict[str, str]
    last_success_at: datetime | None
    failure_count: int


def is_stale(selector_map: SelectorMap) -> bool:
    return selector_map.failure_count >= STALE_AFTER_FAILURES


class ProceduralMemoryRepo:
    def __init__(self, pg_pool: asyncpg.Pool) -> None:
        self.pg_pool = pg_pool

    async def get(self, ats_domain: str) -> SelectorMap | None:
        """A cache hit returns a SelectorMap; a cache miss returns None —
        the two outcomes Step 41's Filler Agent branches on directly.
        """
        row = await self.pg_pool.fetchrow(
            "SELECT ats_domain, field_map_json, last_success_at, failure_count "
            "FROM platform_selector_maps WHERE ats_domain = $1",
            ats_domain,
        )
        if row is None:
            return None
        return SelectorMap(
            ats_domain=row["ats_domain"],
            field_map=json.loads(row["field_map_json"]),
            last_success_at=row["last_success_at"],
            failure_count=row["failure_count"],
        )

    async def record_success(self, ats_domain: str, field_map: dict[str, str]) -> None:
        """Upsert the map that just worked, resetting failure_count — a
        successful fill (whether the first for this domain, or a recovery
        after LLM-assisted DOM analysis found a new working map) is what
        "refreshed" (TDD.md §5) actually means here.
        """
        await self.pg_pool.execute(
            """
            INSERT INTO platform_selector_maps
                (ats_domain, field_map_json, last_success_at, failure_count)
            VALUES ($1, $2::jsonb, now(), 0)
            ON CONFLICT (ats_domain) DO UPDATE SET
                field_map_json = EXCLUDED.field_map_json,
                last_success_at = now(),
                failure_count = 0
            """,
            ats_domain,
            json.dumps(field_map),
        )

    async def record_failure(self, ats_domain: str) -> None:
        """A cached map failed validation on this fill. No row means
        nothing to invalidate — there's no cached map to have failed.
        """
        await self.pg_pool.execute(
            "UPDATE platform_selector_maps SET failure_count = failure_count + 1 "
            "WHERE ats_domain = $1",
            ats_domain,
        )
