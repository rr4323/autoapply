"""Reconstructs a readable JD text block from the Scraper Agent's
structured jd_parsed fields (Step 19/20), for the LLM semantic signal
(Step 28) to read. There's no raw JD text kept anywhere downstream of the
Scraper Agent — parser.py deliberately extracts structured fields instead
of keeping the raw HTML (TDD.md §14: less untrusted surface carried
forward than necessary) — so this is a reconstruction from those fields,
not the original page text.
"""

from __future__ import annotations

from typing import Any


def render_jd_text(jd: dict[str, Any]) -> str:
    sections = []

    if jd.get("title"):
        sections.append(f"Title: {jd['title']}")
    if jd.get("company"):
        sections.append(f"Company: {jd['company']}")
    if jd.get("required_skills"):
        sections.append("Requirements:\n" + "\n".join(f"- {s}" for s in jd["required_skills"]))
    if jd.get("responsibilities"):
        sections.append(
            "Responsibilities:\n" + "\n".join(f"- {r}" for r in jd["responsibilities"])
        )

    return "\n\n".join(sections) if sections else "(no JD details available)"
