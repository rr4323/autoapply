"""SSRF mitigation for every URL the Scraper Agent fetches (TDD.md §14.2).

Applies to Ingestion-Cron-discovered URLs and manually pasted ones alike —
this module doesn't know or care which; that's the caller's job. Order
matters: scheme -> hostname allowlist -> DNS resolve -> resolved-IP check.
The IP-range check happens strictly AFTER resolution, on purpose — domain
allowlisting alone doesn't stop DNS rebinding (a hostname that *looks*
allowlisted but resolves to a private/metadata address), which is exactly
what checking the resolved IP, not just the hostname string, defends against.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlparse

Resolver = Callable[[str], list[str]]


class URLValidationError(Exception):
    """Raised when a URL fails any TDD.md §14.2 check."""


def default_resolver(hostname: str) -> list[str]:
    """Resolve hostname to its IP addresses via real DNS."""
    infos = socket.getaddrinfo(hostname, None)
    return sorted({info[4][0] for info in infos})


def validate_url(
    url: str,
    allowlist: list[str],
    resolver: Resolver = default_resolver,
    allow_insecure_local_targets: bool = False,
) -> None:
    """Raise URLValidationError if url fails any check; return None if clean.

    allow_insecure_local_targets relaxes the https-only and private/
    multicast-IP checks together — off by default, and meant for exactly
    one situation: a local docker-compose demo/E2E run (Step 45) where the
    "ATS" being reached is this project's own fixture server, plain HTTP,
    on the compose network's own private IP space. Every container on
    that network has a private IP by construction, which is indistinguishable
    from a real DNS-rebinding attack to this check — a real deployment
    never sets this; it exists so that fact doesn't have to be silently
    special-cased inside the security check itself.
    """
    parsed = urlparse(url)

    if parsed.scheme != "https" and not allow_insecure_local_targets:
        raise URLValidationError(f"scheme must be https, got {parsed.scheme!r}")

    hostname = parsed.hostname
    if not hostname:
        raise URLValidationError("URL has no hostname")

    if not _hostname_allowed(hostname, allowlist):
        raise URLValidationError(f"hostname {hostname!r} is not in the ATS domain allowlist")

    try:
        resolved_ips = resolver(hostname)
    except OSError as e:
        raise URLValidationError(f"failed to resolve hostname {hostname!r}: {e}") from e

    if not resolved_ips:
        raise URLValidationError(f"hostname {hostname!r} did not resolve to any address")

    if allow_insecure_local_targets:
        return

    for ip_str in resolved_ips:
        ip = ipaddress.ip_address(ip_str)
        # is_private already covers RFC1918, loopback, link-local, and the
        # cloud-metadata range (169.254.169.254) — verified directly against
        # Python's ipaddress module before relying on it here. Multicast
        # isn't a subset of is_private, so it needs its own check.
        if ip.is_private or ip.is_multicast:
            raise URLValidationError(
                f"hostname {hostname!r} resolves to disallowed address {ip_str} "
                "(private/loopback/link-local/metadata/multicast range)"
            )


def _hostname_allowed(hostname: str, allowlist: list[str]) -> bool:
    hostname = hostname.lower()
    for domain in allowlist:
        domain = domain.lower()
        if hostname == domain or hostname.endswith("." + domain):
            return True
    return False
