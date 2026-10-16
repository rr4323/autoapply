"""JD fetcher — timeouts, response size cap, content-type check
(docs/BACKEND_BUILD_STEPS.md Step 19).

Deliberately doesn't do SSRF/allowlist validation — that's
scraper.url_validator's job. Whoever orchestrates a fetch calls
validate_url(url, allowlist) first, then fetch_jd_html(url, client);
kept as two separate functions since "is this URL safe to fetch" and
"actually fetch it" are different concerns TDD.md §14.2 doesn't couple.
"""

from __future__ import annotations

import httpx

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_BYTES = 2_000_000  # a JD page has no legitimate reason to be bigger
ALLOWED_CONTENT_TYPES = ("text/html",)


class FetchError(Exception):
    """Raised when a fetch fails validation or the request itself fails."""


async def fetch_jd_html(
    url: str,
    client: httpx.AsyncClient,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> str:
    try:
        async with client.stream("GET", url, timeout=timeout, follow_redirects=True) as response:
            response.raise_for_status()

            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type not in ALLOWED_CONTENT_TYPES:
                raise FetchError(f"unexpected content-type {content_type!r}, expected text/html")

            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise FetchError(f"response exceeded {max_bytes} byte cap")
                chunks.append(chunk)

            return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
    except httpx.TimeoutException as e:
        raise FetchError(f"request timed out: {e}") from e
    except httpx.HTTPStatusError as e:
        raise FetchError(f"unexpected status {e.response.status_code}") from e
    except httpx.RequestError as e:
        raise FetchError(f"request failed: {e}") from e
