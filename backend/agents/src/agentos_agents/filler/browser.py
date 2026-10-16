"""Ephemeral browser context per fill, egress restricted to the target
ATS domain (docs/BACKEND_BUILD_STEPS.md Step 41, TDD.md §14.3): "no
persistent profile, no cookies or local storage shared across users ...
Egress from that context is restricted to the target ATS domain for the
duration of the fill." A fresh `browser.new_context()` per fill and
closing it immediately after is what actually provides the isolation —
not a rule the browser is asked to follow, a property of never reusing
one context across two fills.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Route


@asynccontextmanager
async def ephemeral_context(browser: Browser, allowed_domain: str) -> AsyncIterator[BrowserContext]:
    context = await browser.new_context()
    try:
        await context.route("**/*", _egress_filter(allowed_domain))
        yield context
    finally:
        await context.close()


def _egress_filter(allowed_domain: str):
    async def handler(route: Route) -> None:
        hostname = urlparse(route.request.url).hostname or ""
        if hostname == allowed_domain or hostname.endswith("." + allowed_domain):
            await route.continue_()
        else:
            await route.abort()

    return handler
