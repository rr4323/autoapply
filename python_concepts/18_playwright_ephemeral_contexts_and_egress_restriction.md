# Playwright: One Browser, Many Isolated Contexts, Restricted Egress

## What it is

Step 41 is the first browser-automation code in this project. Playwright's model has two layers that matter here: a `Browser` (one actual browser process — expensive to start, meant to be reused) and a `BrowserContext` (a cheap, fully isolated "profile" — its own cookies, storage, cache — created from that browser and thrown away). TDD.md §14.3's requirement ("a fresh, ephemeral browser context per fill... no cookies or local storage shared across users") maps onto this directly: one `Browser` for the whole agent process, one new `BrowserContext` per fill, closed immediately after.

## Verified example (from `backend/agents/src/agentos_agents/filler/browser.py`)

```python
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
```

`context.route("**/*", handler)` intercepts **every** network request the context makes — not just page navigations, but every script, iframe, image, and XHR — and the handler decides `continue_()` (let it through) or `abort()` (block it). This is what makes the egress restriction a real boundary rather than a page-level convention: a request the page's own JavaScript initiates (a third-party script tag, a tracking pixel, an iframe) is intercepted exactly the same way a top-level navigation would be.

## Two properties, two different tests

**Isolation** — proven by writing to `localStorage` inside one context and checking a second, independent context can't see it:
```python
async with ephemeral_context(browser, domain) as context:
    page = await context.new_page()
    await page.evaluate("() => localStorage.setItem('leaked_marker', 'from_fill_one')")

async with ephemeral_context(browser, domain) as context:  # a fresh context
    page = await context.new_page()
    leaked = await page.evaluate("() => localStorage.getItem('leaked_marker')")
assert leaked is None
```

**Egress restriction** — proven against a *real* cross-origin reference, not a synthetic one: `ats-fixtures/captcha/index.html` (Step 39) genuinely loads `https://www.google.com/recaptcha/api.js` and an iframe from the same host. Listening for Playwright's `requestfailed` event and asserting a `google.com` URL shows up there is direct evidence the abort actually happened, not just that the code *would* abort it in theory:
```python
page.on("requestfailed", lambda request: failed_urls.append(request.url))
await page.goto(f"{ats_fixtures_url}/captcha/", wait_until="networkidle")
assert any("google.com" in url for url in failed_urls)
```

## `async_api` vs. `sync_api`

Playwright ships both a sync and an async Python API. Every other I/O call in this codebase is already `async`/`await` (httpx, asyncpg, redis.asyncio) — `playwright.async_api` is the one that composes with that, not `playwright.sync_api` (which runs its own internal event loop and can't be awaited from inside an existing one).

## Standard use case

Any browser automation that touches more than one "identity" in the same process — different users, different applications, different untrusted target sites — where state leaking between runs or an untrusted page reaching an unintended host would be a real security problem, not just a correctness inconvenience.
