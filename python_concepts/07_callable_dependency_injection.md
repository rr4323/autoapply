# Dependency Injection via a Callable Default — Python's Lighter-Weight `Pinger`

## What it is

[go_concepts/08_testable_interfaces.md](../go_concepts/08_testable_interfaces.md) covered Go's pattern: define a narrow interface, pass a fake implementation in tests. Python has an even lighter version available when the "interface" is really just one function: accept a plain function as a parameter, with the real implementation as its default value. No `ABC`, no `Protocol`, no class at all needed — [06_abstract_base_classes.md](06_abstract_base_classes.md)'s machinery is for when a dependency has *several* related methods (like `Consumer.handle`); a single-function dependency doesn't need it.

## Verified example (from `backend/agents/src/agentos_agents/scraper/url_validator.py`)

```python
from collections.abc import Callable

Resolver = Callable[[str], list[str]]

def default_resolver(hostname: str) -> list[str]:
    """Resolve hostname to its IP addresses via real DNS."""
    infos = socket.getaddrinfo(hostname, None)
    return sorted({info[4][0] for info in infos})

def validate_url(url: str, allowlist: list[str], resolver: Resolver = default_resolver) -> None:
    # ... uses resolver(hostname) internally, never imports socket directly
    # for the actual DNS call inside this function
```

**Production code never passes `resolver`** — it just calls `validate_url(url, allowlist)` and gets real DNS resolution via the default. **Tests always pass a fake**:
```python
def resolver_returning(*ips: str):
    def _resolver(hostname: str) -> list[str]:
        return list(ips)
    return _resolver

def test_dns_rebinding_hostname_passes_allowlist_but_resolves_private():
    with pytest.raises(URLValidationError, match="disallowed address"):
        validate_url(
            "https://boards.greenhouse.io/jobs/1",
            ALLOWLIST,
            resolver=resolver_returning("169.254.169.254"),
        )
```
Verified: all 17 test cases run in 0.02s, zero real network calls, including the DNS-rebinding scenario — a hostname that's legitimately allowlisted by name but whose (faked) resolution returns a cloud-metadata IP.

## Reading the pieces

- **`Callable[[str], list[str]]`** — a type alias describing "any function taking a `str`, returning a `list[str]`." This is a structural type, same spirit as Go's interfaces ([go_concepts/04_interfaces.md](../go_concepts/04_interfaces.md)) — Python doesn't care whether you pass a named function, a lambda, or a closure, only that it matches this call signature.
- **`resolver: Resolver = default_resolver`** — the default *is* the production behavior. Callers needing the default do nothing differently; callers needing a fake pass one explicitly. This reads naturally at every call site — no wrapper struct, no `NewValidator(resolver)` constructor to thread through.
- **`resolver_returning(*ips)`** — a tiny factory that builds a fake resolver closing over fixed IPs, the same closure idea from [go_concepts/19_closures_and_middleware.md](../go_concepts/19_closures_and_middleware.md), just simpler since there's no wrapping/layering needed — one function in, one function out.

## When to reach for this vs. `ABC`

| Shape of the dependency | Use |
|---|---|
| One function (DNS resolution, a single API call, a clock) | Callable default parameter — this pattern |
| Several related methods that must be implemented together (a consumer's `handle`, a repository's CRUD methods) | `ABC` + `@abstractmethod` ([06_abstract_base_classes.md](06_abstract_base_classes.md)) |

## Standard use case

Anywhere a pure function needs one piece of "the outside world" — network calls, the current time, random values, file I/O — and faking that one thing is all a test needs to control the whole scenario deterministically.
