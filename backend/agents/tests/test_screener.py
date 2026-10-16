from pathlib import Path

import pytest

from agentos_agents.scraper.parser import UnsupportedATSError
from agentos_agents.scraper.screener import FieldType, extract_screener_questions

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_greenhouse_questions_infers_types():
    html = (FIXTURES / "greenhouse_job.html").read_text()

    questions = extract_screener_questions(html, "boards.greenhouse.io")

    assert [(q.question, q.field_type) for q in questions] == [
        ("Why are you interested in this role?", FieldType.FREE_TEXT),
        ("How many years of experience do you have with Go?", FieldType.NUMERIC),
        ("Are you legally authorized to work in the country of this job?", FieldType.YES_NO),
    ]
    assert questions[2].options == ["Yes", "No"]
    assert questions[0].options == []  # free_text/numeric/date carry no options


def test_extract_lever_questions_infers_types():
    html = (FIXTURES / "lever_job.html").read_text()

    questions = extract_screener_questions(html, "jobs.lever.co")

    assert [(q.question, q.field_type) for q in questions] == [
        ("When are you available to start?", FieldType.DATE),
        ("What is your preferred work arrangement?", FieldType.ENUM),
    ]
    assert questions[1].options == ["Remote", "Hybrid", "Onsite"]


def test_extract_screener_questions_rejects_unsupported_ats():
    with pytest.raises(UnsupportedATSError):
        extract_screener_questions("<html></html>", "careers.example.com")
