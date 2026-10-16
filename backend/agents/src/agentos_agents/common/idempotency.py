"""application_events as the idempotency ledger (TDD.md §4.2): a consumer's
side effect is keyed on job_id + event_type, so a redelivered message is a
no-op if that pair was already recorded. Shared here rather than
duplicated per agent, since every consumer needs exactly this same check
against exactly this same table.
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg


class ApplicationEventsIdempotency:
    def __init__(self, pool: asyncpg.Pool, event_type: str, agent_name: str) -> None:
        self.pool = pool
        self.event_type = event_type
        self.agent_name = agent_name

    async def already_handled(self, application_id: str) -> bool:
        row = await self.pool.fetchrow(
            "SELECT 1 FROM application_events WHERE application_id = $1::uuid AND event_type = $2",
            application_id,
            self.event_type,
        )
        return row is not None

    async def record(self, application_id: str, payload: dict[str, Any]) -> None:
        await self.pool.execute(
            """
            INSERT INTO application_events
                (application_id, event_type, produced_by_agent, payload_json)
            VALUES ($1::uuid, $2, $3, $4::jsonb)
            """,
            application_id,
            self.event_type,
            self.agent_name,
            json.dumps(payload),
        )
