"""Bot-check detector (docs/BACKEND_BUILD_STEPS.md Step 42, TDD.md §7.4):
a pure function over a DOM snapshot — no browser, no I/O — run by the
Verifier Agent (Step 43) immediately pre-submit. "Any match is treated as
bot-check present": every check below is deliberately generous, not
precise, because TDD.md §7.4 states the fail-safe direction explicitly —
"false positives ... are the accepted failure direction — it only costs
a manual click, never an unwanted auto-submit." A missed real bot-check
(a false negative) is the failure this function exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from bs4 import BeautifulSoup

# Known CAPTCHA/bot-check vendor hosts (substring match against script
# `src`/iframe `src`, deliberately loose per the false-positive-accepted
# stance above — a partial match still counts).
CAPTCHA_VENDOR_HOSTS = [
    "google.com/recaptcha",
    "gstatic.com/recaptcha",
    "hcaptcha.com",
    "challenges.cloudflare.com",
    "funcaptcha.com",
    "arkoselabs.com",
]

# Hostname substrings suggesting a verification/challenge page, for the
# redirect-based signal.
VERIFICATION_HOSTNAME_KEYWORDS = ("verify", "challenge", "captcha", "checkpoint")

# Input/textarea types that are normally, legitimately hidden (CSRF
# tokens, form state) — excluded from honeypot detection specifically so
# every ordinary form with a hidden CSRF field doesn't trip a false
# positive on essentially every page.
_LEGITIMATELY_HIDDEN_INPUT_TYPES = {"hidden", "submit", "button"}


@dataclass
class BotCheckDetection:
    detected: bool
    signals: list[str] = field(default_factory=list)


def detect_bot_check(html: str, current_url: str, expected_domain: str) -> BotCheckDetection:
    soup = BeautifulSoup(html, "lxml")

    signals: list[str] = []
    signals += _find_vendor_scripts(soup)
    signals += _find_vendor_iframes(soup)
    signals += _find_sitekey_attributes(soup)
    signals += _find_honeypot_fields(soup)

    redirect_signal = _find_verification_redirect(current_url, expected_domain)
    if redirect_signal:
        signals.append(redirect_signal)

    return BotCheckDetection(detected=len(signals) > 0, signals=signals)


def _find_vendor_scripts(soup: BeautifulSoup) -> list[str]:
    signals = []
    for script in soup.find_all("script", src=True):
        src = script["src"]
        if any(vendor in src for vendor in CAPTCHA_VENDOR_HOSTS):
            signals.append(f"known CAPTCHA vendor script: {src!r}")
    return signals


def _find_vendor_iframes(soup: BeautifulSoup) -> list[str]:
    signals = []
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src", "")
        title = iframe.get("title", "")
        if any(vendor in src for vendor in CAPTCHA_VENDOR_HOSTS) or "captcha" in title.lower():
            signals.append(f"CAPTCHA-looking iframe: src={src!r} title={title!r}")
    return signals


def _find_sitekey_attributes(soup: BeautifulSoup) -> list[str]:
    signals = []
    for tag in soup.find_all(attrs={"data-sitekey": True}):
        signals.append(f"data-sitekey attribute present on <{tag.name}>")
    return signals


def _find_honeypot_fields(soup: BeautifulSoup) -> list[str]:
    signals = []
    for tag in soup.find_all(["input", "textarea"]):
        input_type = (tag.get("type") or "text").lower()
        if tag.name == "input" and input_type in _LEGITIMATELY_HIDDEN_INPUT_TYPES:
            continue
        if _is_hidden(tag) or _is_hidden(tag.find_parent(["li", "div", "label"])):
            name = tag.get("name") or tag.get("id") or "?"
            signals.append(f"honeypot-shaped hidden field: <{tag.name} name={name!r}>")
    return signals


def _is_hidden(tag) -> bool:
    if tag is None:
        return False
    style = (tag.get("style") or "").replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return True
    return tag.get("aria-hidden", "").lower() == "true"


def _find_verification_redirect(current_url: str, expected_domain: str) -> str | None:
    hostname = urlparse(current_url).hostname or ""
    if hostname == expected_domain or hostname.endswith("." + expected_domain):
        return None
    if any(keyword in hostname.lower() for keyword in VERIFICATION_HOSTNAME_KEYWORDS):
        return f"redirected to a verification-looking host: {hostname!r}"
    return f"redirected away from expected domain {expected_domain!r} to {hostname!r}"
