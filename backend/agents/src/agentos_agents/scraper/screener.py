"""Screener-question extraction + field-type inference (docs/BACKEND_BUILD_STEPS.md
Step 20, TDD.md §6.5).

§6.5 splits the work in two: the Scraper Agent (here) infers each question's
*expected* field type from the JD/DOM at parse time; the Generator Agent
(Step 37, built later) checks its *answer* against that type before a
document is marked ready. This module only does the first half — read a
question widget, say what shape an answer should take.

Verified against the same representative fixtures as parser.py, extended
with an application-questions section each (not scraped from a live page —
same caveat as parser.py's docstring).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from bs4 import BeautifulSoup, Tag

from agentos_agents.scraper.parser import UnsupportedATSError


class FieldType(StrEnum):
    FREE_TEXT = "free_text"
    YES_NO = "yes_no"
    NUMERIC = "numeric"
    DATE = "date"
    ENUM = "enum"


@dataclass
class ScreenerQuestion:
    question: str
    field_type: FieldType
    # Non-empty only for YES_NO/ENUM (the select-backed types) — the
    # actual allowed values, captured here specifically because Step 37's
    # answer validator needs to check an enum answer against real choices,
    # not just "is this non-empty text of a reasonable length."
    options: list[str] = field(default_factory=list)


def extract_screener_questions(html: str, ats_domain: str) -> list[ScreenerQuestion]:
    domain = ats_domain.lower()
    soup = BeautifulSoup(html, "lxml")
    if "greenhouse" in domain:
        return _extract_greenhouse_questions(soup)
    if "lever" in domain:
        return _extract_lever_questions(soup)
    raise UnsupportedATSError(f"no screener extractor for ATS domain {ats_domain!r}")


def _extract_greenhouse_questions(soup: BeautifulSoup) -> list[ScreenerQuestion]:
    questions = []
    for entry in soup.select("#application_form li.field"):
        label = entry.find("label")
        widget = entry.find(["input", "select", "textarea"])
        if not label or not widget:
            continue
        field_type, options = _infer_field(widget)
        questions.append(
            ScreenerQuestion(
                question=label.get_text(strip=True), field_type=field_type, options=options
            )
        )
    return questions


def _extract_lever_questions(soup: BeautifulSoup) -> list[ScreenerQuestion]:
    questions = []
    for entry in soup.select(".application-question"):
        label = entry.find(class_="application-label")
        widget = entry.find(["input", "select", "textarea"])
        if not label or not widget:
            continue
        field_type, options = _infer_field(widget)
        questions.append(
            ScreenerQuestion(
                question=label.get_text(strip=True), field_type=field_type, options=options
            )
        )
    return questions


def _infer_field(widget: Tag) -> tuple[FieldType, list[str]]:
    if widget.name == "textarea":
        return FieldType.FREE_TEXT, []

    if widget.name == "select":
        options = [
            opt.get_text(strip=True)
            for opt in widget.find_all("option")
            if opt.get_text(strip=True)
        ]
        if {o.lower() for o in options} == {"yes", "no"}:
            return FieldType.YES_NO, options
        return FieldType.ENUM, options

    if widget.name == "input":
        input_type = (widget.get("type") or "text").lower()
        if input_type == "number":
            return FieldType.NUMERIC, []
        if input_type == "date":
            return FieldType.DATE, []
        return FieldType.FREE_TEXT, []

    raise ValueError(f"unrecognized question widget <{widget.name}>")
