"""Message envelope contract shared with the Go control plane.

See ../../../../contracts/envelope.md for the source of truth both
implementations follow.
"""

from pydantic import BaseModel


class Envelope(BaseModel):
    job_id: str
    trace_id: str
    event_type: str
    produced_by: str
    timestamp: str
    payload_ref: str


def working_memory_key(job_id: str, stage: str) -> str:
    """Build the working-memory key scheme from TDD.md §5."""
    return f"working_memory:job:{job_id}:{stage}"
