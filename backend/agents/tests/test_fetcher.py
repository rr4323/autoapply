import httpx
import pytest
import respx

from agentos_agents.scraper.fetcher import FetchError, fetch_jd_html

URL = "https://boards.greenhouse.io/example/jobs/1"


@respx.mock
async def test_fetch_success():
    respx.get(URL).mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/html"}, text="<html>ok</html>"
        )
    )

    async with httpx.AsyncClient() as client:
        html = await fetch_jd_html(URL, client)

    assert html == "<html>ok</html>"


@respx.mock
async def test_fetch_rejects_wrong_content_type():
    respx.get(URL).mock(
        return_value=httpx.Response(200, headers={"content-type": "application/json"}, text="{}")
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(FetchError, match="content-type"):
            await fetch_jd_html(URL, client)


@respx.mock
async def test_fetch_rejects_oversized_response():
    big_body = "x" * 1000
    respx.get(URL).mock(
        return_value=httpx.Response(200, headers={"content-type": "text/html"}, text=big_body)
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(FetchError, match="byte cap"):
            await fetch_jd_html(URL, client, max_bytes=100)


@respx.mock
async def test_fetch_rejects_http_error_status():
    respx.get(URL).mock(return_value=httpx.Response(404))

    async with httpx.AsyncClient() as client:
        with pytest.raises(FetchError, match="404"):
            await fetch_jd_html(URL, client)


@respx.mock
async def test_fetch_rejects_timeout():
    respx.get(URL).mock(side_effect=httpx.TimeoutException("timed out"))

    async with httpx.AsyncClient() as client:
        with pytest.raises(FetchError, match="timed out"):
            await fetch_jd_html(URL, client)
