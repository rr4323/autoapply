# A `testcontainers` Readiness-Probe Gotcha: Root Path, Not Your Actual Content

## What happened

Step 39 needed to prove the local ATS fixture forms (`ats-fixtures/clean/index.html`, `ats-fixtures/captcha/index.html` — no file at the root) are reachable. The obvious test: spin the same nginx-serving-a-directory setup via `testcontainers.community.nginx.NginxContainer`, hit `/clean/` and `/captcha/`, assert `200`. The test **hung indefinitely** instead of failing or passing.

## Why

```python
class NginxContainer(DockerContainer):
    def start(self) -> Self:
        super().start()
        host = self.get_container_host_ip()
        port = str(self.get_exposed_port(self.port))
        self._connect(host, port)   # <-- runs automatically, always
        return self

    @wait_container_is_ready(urllib.error.URLError)
    def _connect(self, host, port) -> None:
        url = urllib.parse.urlunsplit(("http", f"{host}:{port}", "", "", ""))
        urllib.request.urlopen(url, timeout=1)   # <-- always checks "/", not your path
```

`NginxContainer.start()` unconditionally probes the container **root** (`/`) as its readiness check — there's no constructor option to point it elsewhere. This project's `ats-fixtures` directory had content only under `/clean/` and `/captcha/`, so nginx's default behavior (no index file, autoindex off) returned `403` at `/`. `urllib.request.urlopen` raises `HTTPError` for a `403` — which **is** a subclass of `URLError` — so `@wait_container_is_ready(urllib.error.URLError)` caught it and retried... forever, since the response was never going to change. Confirmed with `inspect.getsource(NginxContainer)` before chasing the wrong theory.

## The fix

Add a trivial `ats-fixtures/index.html` landing page so `GET /` returns `200` immediately. This isn't a workaround bolted onto the test — it's a real, useful addition to the fixture service itself (a human hitting the compose port gets a helpful landing page instead of a bare 403), which happens to also satisfy the readiness probe. Once added, `test_ats_fixtures.py`'s 3 tests passed in under 4 seconds.

## The general lesson

When a `testcontainers` module wraps a specific application (nginx, Postgres, Redis, MinIO), its default readiness check is convention-based, not content-aware — it doesn't know what *your* deployment actually serves. `wait_container_is_ready`-style decorators retry on a specified exception type indefinitely (no visible timeout in the hang itself), so a readiness check that can structurally never succeed produces a **hang**, not a **clear failure** — worth recognizing that signature quickly (test makes zero progress, no error, no timeout) rather than assuming the container itself is broken. The earlier Postgres "restarts once after init scripts" wait-strategy fix ([python_concepts/10_asyncpg_and_python_testcontainers.md](10_asyncpg_and_python_testcontainers.md)) was the same category of lesson: read the actual wait-strategy source before assuming the default is content-aware.

## Standard use case

Any time a `testcontainers` module's default `start()`/readiness behavior doesn't match your actual served content (a root-less static site, a custom health endpoint, an app that isn't ready until a specific log line) — check the module's source for what it actually waits on before trusting it, the same "verify before relying on it" habit this project has applied to library behavior throughout (`pgx` UUID scanning, Redis `SET`/TTL semantics, Python's `ipaddress` classification, and now this).
