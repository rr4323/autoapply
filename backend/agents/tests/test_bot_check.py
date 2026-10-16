"""docs/BACKEND_BUILD_STEPS.md Step 42: bot-check detector, both directions
against the real Step 39 fixture DOMs — a pure function, no browser/Docker
needed.
"""

from pathlib import Path

from agentos_agents.filler.bot_check import detect_bot_check

ATS_FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "ats-fixtures"
CLEAN_HTML = (ATS_FIXTURES_DIR / "clean" / "index.html").read_text()
CAPTCHA_HTML = (ATS_FIXTURES_DIR / "captcha" / "index.html").read_text()

DOMAIN = "ats-fixtures.local"
CLEAN_URL = f"http://{DOMAIN}/clean/"
CAPTCHA_URL = f"http://{DOMAIN}/captcha/"


def test_clean_fixture_is_not_flagged():
    result = detect_bot_check(CLEAN_HTML, CLEAN_URL, DOMAIN)

    assert result.detected is False
    assert result.signals == []


def test_captcha_fixture_is_flagged():
    result = detect_bot_check(CAPTCHA_HTML, CAPTCHA_URL, DOMAIN)

    assert result.detected is True
    assert result.signals != []


def test_captcha_fixture_vendor_script_detected():
    result = detect_bot_check(CAPTCHA_HTML, CAPTCHA_URL, DOMAIN)

    assert any("vendor script" in s for s in result.signals)


def test_captcha_fixture_vendor_iframe_detected():
    result = detect_bot_check(CAPTCHA_HTML, CAPTCHA_URL, DOMAIN)

    assert any("iframe" in s for s in result.signals)


def test_captcha_fixture_sitekey_detected():
    result = detect_bot_check(CAPTCHA_HTML, CAPTCHA_URL, DOMAIN)

    assert any("data-sitekey" in s for s in result.signals)


def test_captcha_fixture_honeypot_field_detected():
    result = detect_bot_check(CAPTCHA_HTML, CAPTCHA_URL, DOMAIN)

    assert any("honeypot" in s for s in result.signals)


def test_legitimate_hidden_csrf_field_is_not_a_false_positive():
    html = """
    <form>
      <input type="hidden" name="csrf_token" value="abc123" />
      <input type="text" name="first_name" />
    </form>
    """

    result = detect_bot_check(html, CLEAN_URL, DOMAIN)

    assert result.detected is False


def test_verification_redirect_is_detected():
    html = "<html><body>Please verify you are human.</body></html>"
    redirected_url = "http://verify.suspicious-vendor.example/challenge"

    result = detect_bot_check(html, redirected_url, DOMAIN)

    assert result.detected is True
    assert any("verification" in s for s in result.signals)


def test_same_domain_navigation_is_not_flagged_as_a_redirect():
    html = "<html><body>ok</body></html>"
    same_domain_url = f"http://{DOMAIN}/clean/submit"

    result = detect_bot_check(html, same_domain_url, DOMAIN)

    assert result.detected is False


def test_subdomain_of_expected_domain_is_not_flagged_as_a_redirect():
    html = "<html><body>ok</body></html>"
    subdomain_url = f"http://boards.{DOMAIN}/apply"

    result = detect_bot_check(html, subdomain_url, DOMAIN)

    assert result.detected is False
