import json

import fakeredis
import pytest

from agentos_agents.common.publisher import Publisher
from agentos_agents.common.topics import TOPIC_APPLICATION_TERMINAL
from agentos_agents.filler.verify import VerificationResult, publish_terminal_event


@pytest.fixture
def redis_client():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


async def test_publish_terminal_event_submitted(redis_client):
    publisher = Publisher(redis_client)
    result = VerificationResult(
        outcome="submitted", reasons=["clean pass"], bot_check_detected=False
    )

    await publish_terminal_event(publisher, redis_client, "job-1", "trace-1", result)

    entries = await redis_client.xrange(TOPIC_APPLICATION_TERMINAL)
    assert len(entries) == 1
    _entry_id, fields = entries[0]
    assert fields["job_id"] == "job-1"
    assert fields["produced_by"] == "verifier-agent"

    payload = json.loads(await redis_client.get(fields["payload_ref"]))
    assert payload["status"] == "submitted"
    assert payload["bot_check_detected"] is False


async def test_publish_terminal_event_ready_for_review(redis_client):
    publisher = Publisher(redis_client)
    result = VerificationResult(
        outcome="ready_for_review", reasons=["bot-check detected"], bot_check_detected=True
    )

    await publish_terminal_event(publisher, redis_client, "job-2", "trace-2", result)

    entries = await redis_client.xrange(TOPIC_APPLICATION_TERMINAL)
    payload = json.loads(await redis_client.get(entries[0][1]["payload_ref"]))
    assert payload["status"] == "ready_for_review"
    assert payload["reasons"] == ["bot-check detected"]
