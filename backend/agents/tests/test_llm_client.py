import httpx
import pytest
import respx

from agentos_agents.common.llm_client import AnthropicLLMClient, LLMError

URL = "https://api.anthropic.com/v1/messages"


async def instant_sleep(_seconds: float) -> None:
    pass


def message_response(text: str) -> httpx.Response:
    return httpx.Response(200, json={"content": [{"type": "text", "text": text}]})


@respx.mock
async def test_complete_returns_response_text():
    respx.post(URL).mock(return_value=message_response("hello"))

    async with httpx.AsyncClient() as http_client:
        client = AnthropicLLMClient(http_client, api_key="k", sleep=instant_sleep)
        result = await client.complete("system prompt", "user prompt")

    assert result == "hello"


@respx.mock
async def test_complete_retries_on_429_then_succeeds():
    route = respx.post(URL).mock(
        side_effect=[httpx.Response(429), message_response("recovered")]
    )

    async with httpx.AsyncClient() as http_client:
        client = AnthropicLLMClient(http_client, api_key="k", sleep=instant_sleep)
        result = await client.complete("system", "user")

    assert result == "recovered"
    assert route.call_count == 2


@respx.mock
async def test_complete_raises_on_non_429_error_without_retrying():
    route = respx.post(URL).mock(return_value=httpx.Response(500, text="boom"))

    async with httpx.AsyncClient() as http_client:
        client = AnthropicLLMClient(http_client, api_key="k", sleep=instant_sleep)
        with pytest.raises(LLMError, match="500"):
            await client.complete("system", "user")

    assert route.call_count == 1


@respx.mock
async def test_complete_raises_on_unexpected_response_shape():
    respx.post(URL).mock(return_value=httpx.Response(200, json={"unexpected": "shape"}))

    async with httpx.AsyncClient() as http_client:
        client = AnthropicLLMClient(http_client, api_key="k", sleep=instant_sleep)
        with pytest.raises(LLMError, match="unexpected LLM response shape"):
            await client.complete("system", "user")
