import json

import httpx
import pytest
import respx

from agentos_agents.filler.verify import PolicyCallbackClient, PolicyCallbackError

BASE_URL = "http://api.internal:8080"
URL = f"{BASE_URL}/internal/agent/callback"


@respx.mock
async def test_request_submit_sends_expected_request_and_parses_accepted():
    captured = {}

    def responder(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"accepted": True, "action": "submit", "reasons": ["ok"]})

    respx.post(URL).mock(side_effect=responder)

    async with httpx.AsyncClient() as http_client:
        client = PolicyCallbackClient(http_client, BASE_URL, internal_secret="s3cret")
        accepted, reasons = await client.request_submit("job-1", bot_check_detected=False)

    assert accepted is True
    assert reasons == ["ok"]
    assert captured["body"] == {
        "job_id": "job-1",
        "action": "submit",
        "bot_check_detected": False,
    }
    assert captured["headers"]["x-internal-secret"] == "s3cret"


@respx.mock
async def test_request_submit_parses_a_rejected_409_response():
    respx.post(URL).mock(
        return_value=httpx.Response(
            409,
            json={
                "accepted": False,
                "action": "require_review",
                "reasons": ["bot-check detected"],
            },
        )
    )

    async with httpx.AsyncClient() as http_client:
        client = PolicyCallbackClient(http_client, BASE_URL, internal_secret="s3cret")
        accepted, reasons = await client.request_submit("job-1", bot_check_detected=True)

    assert accepted is False
    assert reasons == ["bot-check detected"]


@respx.mock
async def test_request_submit_raises_on_unexpected_status():
    respx.post(URL).mock(return_value=httpx.Response(500, text="boom"))

    async with httpx.AsyncClient() as http_client:
        client = PolicyCallbackClient(http_client, BASE_URL, internal_secret="s3cret")
        with pytest.raises(PolicyCallbackError, match="500"):
            await client.request_submit("job-1", bot_check_detected=False)


@respx.mock
async def test_request_submit_raises_on_connection_failure():
    respx.post(URL).mock(side_effect=httpx.ConnectError("connection refused"))

    async with httpx.AsyncClient() as http_client:
        client = PolicyCallbackClient(http_client, BASE_URL, internal_secret="s3cret")
        with pytest.raises(PolicyCallbackError):
            await client.request_submit("job-1", bot_check_detected=False)
