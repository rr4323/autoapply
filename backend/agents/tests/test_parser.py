from pathlib import Path

import pytest

from agentos_agents.scraper.parser import UnsupportedATSError, parse_jd

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_greenhouse_fixture():
    html = (FIXTURES / "greenhouse_job.html").read_text()

    parsed = parse_jd(html, "boards.greenhouse.io")

    assert parsed.title == "Senior Backend Engineer"
    assert parsed.company == "Acme Corp"
    assert parsed.required_skills == [
        "5+ years of experience with Go or a similar statically-typed language",
        "Strong understanding of distributed systems",
        "Experience with PostgreSQL and Redis",
    ]
    assert parsed.responsibilities == [
        "Design and implement backend services",
        "Own the on-call rotation for your team's services",
        "Mentor junior engineers",
    ]


def test_parse_lever_fixture():
    html = (FIXTURES / "lever_job.html").read_text()

    parsed = parse_jd(html, "jobs.lever.co")

    assert parsed.title == "Senior AI Engineer"
    assert parsed.company == "Beta AI Inc"
    assert parsed.required_skills == [
        "Experience with LLMs and LangChain",
        "Strong Python skills",
        "Familiarity with vector databases",
    ]
    assert parsed.responsibilities == [
        "Build and maintain RAG pipelines",
        "Collaborate with product on agent design",
    ]


def test_parse_jd_rejects_unsupported_ats():
    with pytest.raises(UnsupportedATSError):
        parse_jd("<html></html>", "careers.example.com")
