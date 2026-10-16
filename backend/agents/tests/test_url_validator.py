import pytest

from agentos_agents.scraper.url_validator import URLValidationError, validate_url

ALLOWLIST = ["greenhouse.io", "lever.co"]


def resolver_returning(*ips: str):
    """Build a fake resolver that always returns the given IPs — the
    injected-fake pattern (go_concepts/08_testable_interfaces.md's Python
    counterpart): no real DNS lookups in these tests.
    """

    def _resolver(hostname: str) -> list[str]:
        return list(ips)

    return _resolver


def test_valid_url_passes():
    validate_url(
        "https://boards.greenhouse.io/example/jobs/1",
        ALLOWLIST,
        resolver=resolver_returning("8.8.8.8"),
    )  # no exception


def test_rejects_non_https_scheme():
    with pytest.raises(URLValidationError, match="scheme must be https"):
        validate_url(
            "http://boards.greenhouse.io/example/jobs/1",
            ALLOWLIST,
            resolver=resolver_returning("8.8.8.8"),
        )


def test_rejects_hostname_not_in_allowlist():
    with pytest.raises(URLValidationError, match="not in the ATS domain allowlist"):
        validate_url(
            "https://evil.example.com/jobs/1",
            ALLOWLIST,
            resolver=resolver_returning("8.8.8.8"),
        )


def test_allows_subdomain_of_allowlisted_domain():
    validate_url(
        "https://boards.greenhouse.io/x",
        ALLOWLIST,
        resolver=resolver_returning("8.8.8.8"),
    )  # no exception — boards.greenhouse.io is a subdomain of greenhouse.io


def test_rejects_lookalike_domain_not_actually_a_subdomain():
    # "notgreenhouse.io" is NOT a subdomain of "greenhouse.io" — must not
    # match via a naive suffix check (e.g. hostname.endswith("greenhouse.io")
    # without the leading dot would wrongly allow this).
    with pytest.raises(URLValidationError, match="not in the ATS domain allowlist"):
        validate_url(
            "https://notgreenhouse.io/jobs/1",
            ALLOWLIST,
            resolver=resolver_returning("8.8.8.8"),
        )


@pytest.mark.parametrize(
    "ip,label",
    [
        ("10.0.0.5", "RFC1918 10.0.0.0/8"),
        ("172.16.0.1", "RFC1918 172.16.0.0/12"),
        ("192.168.1.1", "RFC1918 192.168.0.0/16"),
        ("127.0.0.1", "loopback"),
        ("169.254.1.1", "link-local"),
        ("169.254.169.254", "cloud metadata IP"),
        ("224.0.0.1", "multicast"),
    ],
)
def test_rejects_each_private_range(ip, label):
    with pytest.raises(URLValidationError, match="disallowed address"):
        validate_url(
            "https://boards.greenhouse.io/jobs/1",
            ALLOWLIST,
            resolver=resolver_returning(ip),
        )


def test_dns_rebinding_hostname_passes_allowlist_but_resolves_private():
    # The hostname itself is legitimately allowlisted — this is exactly
    # the DNS-rebinding scenario TDD.md §14.2 calls out: allowlisting the
    # string alone would let this through. The IP-range check (running
    # AFTER resolution) is what actually catches it.
    with pytest.raises(URLValidationError, match="disallowed address"):
        validate_url(
            "https://boards.greenhouse.io/jobs/1",
            ALLOWLIST,
            resolver=resolver_returning("169.254.169.254"),
        )


def test_rejects_when_any_resolved_ip_is_bad_even_if_others_are_fine():
    with pytest.raises(URLValidationError, match="disallowed address"):
        validate_url(
            "https://boards.greenhouse.io/jobs/1",
            ALLOWLIST,
            resolver=resolver_returning("8.8.8.8", "10.0.0.5"),
        )


def test_rejects_url_with_no_hostname():
    with pytest.raises(URLValidationError, match="no hostname"):
        validate_url("https:///no-host", ALLOWLIST, resolver=resolver_returning("8.8.8.8"))


def test_rejects_dns_resolution_failure():
    def failing_resolver(hostname: str) -> list[str]:
        raise OSError("name or service not known")

    with pytest.raises(URLValidationError, match="failed to resolve"):
        validate_url("https://boards.greenhouse.io/jobs/1", ALLOWLIST, resolver=failing_resolver)


def test_rejects_empty_resolution_result():
    with pytest.raises(URLValidationError, match="did not resolve"):
        validate_url(
            "https://boards.greenhouse.io/jobs/1", ALLOWLIST, resolver=resolver_returning()
        )


def test_allow_insecure_local_targets_permits_http_scheme():
    validate_url(  # must not raise
        "http://boards.greenhouse.io/jobs/1",
        ALLOWLIST,
        resolver=resolver_returning("172.20.0.5"),
        allow_insecure_local_targets=True,
    )


def test_allow_insecure_local_targets_permits_private_resolved_ip():
    validate_url(  # must not raise, unlike the plain-mode private-IP tests above
        "https://boards.greenhouse.io/jobs/1",
        ALLOWLIST,
        resolver=resolver_returning("172.20.0.5"),
        allow_insecure_local_targets=True,
    )


def test_allow_insecure_local_targets_still_enforces_the_allowlist():
    # The relaxation is scheme + private-IP only — an unallowlisted host
    # is rejected exactly as before, demo mode or not.
    with pytest.raises(URLValidationError, match="allowlist"):
        validate_url(
            "http://not-an-allowed-host.example.com/jobs/1",
            ALLOWLIST,
            resolver=resolver_returning("172.20.0.5"),
            allow_insecure_local_targets=True,
        )


def test_allow_insecure_local_targets_defaults_to_false():
    with pytest.raises(URLValidationError, match="scheme must be https"):
        validate_url(
            "http://boards.greenhouse.io/jobs/1",
            ALLOWLIST,
            resolver=resolver_returning("172.20.0.5"),
        )
