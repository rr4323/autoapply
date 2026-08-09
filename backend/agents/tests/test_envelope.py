from pathlib import Path

import pytest
from pydantic import ValidationError

from agentos_agents.common.envelope import Envelope, working_memory_key

GOLDEN_FIXTURE = (
    Path(__file__).parent.parent.parent / "contracts" / "testdata" / "envelope_golden.json"
)


def sample_envelope() -> Envelope:
    return Envelope(
        job_id="b7e6c2b4-3f1a-4c9e-9d2a-1a2b3c4d5e6f",
        trace_id="f1e2d3c4-b5a6-4978-8a1b-2c3d4e5f6789",
        event_type="jd.parsed",
        produced_by="scraper-agent",
        timestamp="2026-08-09T14:00:00Z",
        payload_ref="working_memory:job:b7e6c2b4-3f1a-4c9e-9d2a-1a2b3c4d5e6f:jd_parsed",
    )


def test_envelope_round_trip():
    original = sample_envelope()

    json_str = original.model_dump_json()
    decoded = Envelope.model_validate_json(json_str)

    assert decoded == original


def test_envelope_rejects_missing_job_id():
    data = sample_envelope().model_dump()
    del data["job_id"]

    with pytest.raises(ValidationError):
        Envelope.model_validate(data)


def test_envelope_rejects_missing_trace_id():
    data = sample_envelope().model_dump()
    del data["trace_id"]

    with pytest.raises(ValidationError):
        Envelope.model_validate(data)


def test_envelope_golden_fixture():
    decoded = Envelope.model_validate_json(GOLDEN_FIXTURE.read_text())

    assert decoded == sample_envelope()


def test_working_memory_key():
    got = working_memory_key("b7e6c2b4-3f1a-4c9e-9d2a-1a2b3c4d5e6f", "jd_parsed")
    want = "working_memory:job:b7e6c2b4-3f1a-4c9e-9d2a-1a2b3c4d5e6f:jd_parsed"

    assert got == want
