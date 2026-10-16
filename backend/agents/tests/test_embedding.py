import httpx
import pytest
import respx

from agentos_agents.retriever.embedding import EmbeddingError, OpenAIEmbeddingClient

URL = "https://api.openai.com/v1/embeddings"


async def instant_sleep(_seconds: float) -> None:
    pass  # tests shouldn't actually wait through exponential backoff


def embeddings_response(pairs: list[tuple[int, list[float]]]) -> httpx.Response:
    return httpx.Response(
        200, json={"data": [{"index": i, "embedding": vec} for i, vec in pairs]}
    )


@respx.mock
async def test_embed_batch_empty_input_makes_no_network_call():
    route = respx.post(URL)
    async with httpx.AsyncClient() as http_client:
        client = OpenAIEmbeddingClient(http_client, api_key="k", sleep=instant_sleep)
        result = await client.embed_batch([])

    assert result == []
    assert route.call_count == 0


@respx.mock
async def test_embed_batch_restores_input_order_even_if_response_is_out_of_order():
    respx.post(URL).mock(
        return_value=embeddings_response([(1, [0.2, 0.2]), (0, [0.1, 0.1])])
    )

    async with httpx.AsyncClient() as http_client:
        client = OpenAIEmbeddingClient(http_client, api_key="k", sleep=instant_sleep)
        result = await client.embed_batch(["first", "second"])

    assert result == [[0.1, 0.1], [0.2, 0.2]]


@respx.mock
async def test_embed_batch_retries_on_429_then_succeeds():
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(429),
            embeddings_response([(0, [0.5])]),
        ]
    )

    async with httpx.AsyncClient() as http_client:
        client = OpenAIEmbeddingClient(
            http_client, api_key="k", max_retries=3, sleep=instant_sleep
        )
        result = await client.embed_batch(["only"])

    assert result == [[0.5]]
    assert route.call_count == 3


@respx.mock
async def test_embed_batch_raises_after_exhausting_retries():
    route = respx.post(URL).mock(return_value=httpx.Response(429))

    async with httpx.AsyncClient() as http_client:
        client = OpenAIEmbeddingClient(
            http_client, api_key="k", max_retries=2, sleep=instant_sleep
        )
        with pytest.raises(EmbeddingError, match="rate limited"):
            await client.embed_batch(["only"])

    assert route.call_count == 3  # initial attempt + 2 retries, then give up


@respx.mock
async def test_embed_batch_does_not_retry_on_non_429_error():
    route = respx.post(URL).mock(return_value=httpx.Response(500, text="server error"))

    async with httpx.AsyncClient() as http_client:
        client = OpenAIEmbeddingClient(
            http_client, api_key="k", max_retries=3, sleep=instant_sleep
        )
        with pytest.raises(EmbeddingError, match="500"):
            await client.embed_batch(["only"])

    assert route.call_count == 1


@respx.mock
async def test_embed_batch_invokes_on_call_hook_per_attempt():
    respx.post(URL).mock(
        side_effect=[httpx.Response(429), embeddings_response([(0, [0.1])])]
    )
    calls: list[tuple[str, int, int]] = []

    async with httpx.AsyncClient() as http_client:
        client = OpenAIEmbeddingClient(
            http_client,
            api_key="k",
            model="text-embedding-3-small",
            sleep=instant_sleep,
            on_call=lambda model, count, attempt: calls.append((model, count, attempt)),
        )
        await client.embed_batch(["only"])

    assert calls == [
        ("text-embedding-3-small", 1, 1),
        ("text-embedding-3-small", 1, 2),
    ]
