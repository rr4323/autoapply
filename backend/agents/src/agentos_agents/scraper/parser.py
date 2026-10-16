"""HTML -> structured JD fields, per ATS domain (docs/BACKEND_BUILD_STEPS.md
Step 19). Simplified, per-ATS CSS selectors — screener-question extraction
is Step 20, layered on top of this, not part of it.

Verified against the representative fixtures in tests/fixtures/, not a
real scraped page (no network access in this environment) — TDD.md §16
already names this exact limitation: "the first fill on any new domain
still depends on LLM-assisted DOM analysis, which can fail on unusual
layouts." This parser doesn't remove that risk, only handles the common
documented case for each platform.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup


class UnsupportedATSError(Exception):
    """Raised when ats_domain doesn't match a known parser."""


@dataclass
class ParsedJD:
    title: str | None = None
    company: str | None = None
    required_skills: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)


def parse_jd(html: str, ats_domain: str) -> ParsedJD:
    domain = ats_domain.lower()
    if "greenhouse" in domain:
        return _parse_greenhouse(html)
    if "lever" in domain:
        return _parse_lever(html)
    raise UnsupportedATSError(f"no parser for ATS domain {ats_domain!r}")


def _parse_greenhouse(html: str) -> ParsedJD:
    soup = BeautifulSoup(html, "lxml")
    return ParsedJD(
        title=_text(soup, "h1.app-title"),
        company=_text(soup, ".company-name"),
        required_skills=_list_after_heading(soup, "Requirements"),
        responsibilities=_list_after_heading(soup, "Responsibilities"),
    )


def _parse_lever(html: str) -> ParsedJD:
    soup = BeautifulSoup(html, "lxml")
    return ParsedJD(
        title=_text(soup, ".posting-headline h2"),
        company=_company_from_title_tag(soup),
        required_skills=_list_after_heading(soup, "Requirements"),
        responsibilities=_list_after_heading(soup, "Responsibilities"),
    )


def _text(soup: BeautifulSoup, selector: str) -> str | None:
    tag = soup.select_one(selector)
    return tag.get_text(strip=True) if tag else None


def _company_from_title_tag(soup: BeautifulSoup) -> str | None:
    # Real Lever pages don't embed the company name in the posting body
    # (it lives in the URL path, jobs.lever.co/{company}/...) — the
    # <title> tag convention ("Role - Company") is the honest source
    # here, not a fabricated body-content selector.
    title_tag = soup.find("title")
    if not title_tag:
        return None
    text = title_tag.get_text(strip=True)
    if " - " in text:
        return text.rsplit(" - ", 1)[-1].strip()
    return None


def _list_after_heading(soup: BeautifulSoup, heading_text: str) -> list[str]:
    """Find any heading-like tag whose exact text matches heading_text,
    then return the <li> texts of the next <ul> in document order — works
    whether the <ul> is a sibling (Greenhouse's markup) or nested inside
    a wrapper div (Lever's), since find_next traverses the whole
    subsequent document, not just immediate siblings.
    """
    target = heading_text.strip().lower()
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "strong", "b"]):
        if tag.get_text(strip=True).lower() == target:
            ul = tag.find_next("ul")
            if ul:
                return [li.get_text(strip=True) for li in ul.find_all("li")]
    return []
