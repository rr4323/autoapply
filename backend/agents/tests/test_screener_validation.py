from agentos_agents.generator.screener_validation import (
    MAX_FREE_TEXT_LENGTH,
    needs_input,
    validate_screener_answer,
    validate_screener_answers,
)
from agentos_agents.scraper.screener import FieldType


def test_numeric_field_rejects_prose():
    result = validate_screener_answer(FieldType.NUMERIC, "quite a few years actually")

    assert result.valid is False
    assert result.reason == "answer is not numeric"


def test_numeric_field_accepts_a_number():
    assert validate_screener_answer(FieldType.NUMERIC, "5").valid is True
    assert validate_screener_answer(FieldType.NUMERIC, "5.5").valid is True


def test_free_text_field_rejects_over_length_answer():
    over_length = "x" * (MAX_FREE_TEXT_LENGTH + 1)

    result = validate_screener_answer(FieldType.FREE_TEXT, over_length)

    assert result.valid is False
    assert "exceeds" in result.reason


def test_free_text_field_accepts_reasonable_length_answer():
    result = validate_screener_answer(FieldType.FREE_TEXT, "I'm excited about this role because...")

    assert result.valid is True


def test_yes_no_field_rejects_prose():
    result = validate_screener_answer(FieldType.YES_NO, "Sure, I think so")

    assert result.valid is False
    assert result.reason == "answer is not yes/no"


def test_yes_no_field_accepts_case_insensitive_yes_or_no():
    assert validate_screener_answer(FieldType.YES_NO, "Yes").valid is True
    assert validate_screener_answer(FieldType.YES_NO, "no").valid is True


def test_date_field_rejects_non_iso_format():
    result = validate_screener_answer(FieldType.DATE, "next Monday")

    assert result.valid is False
    assert "ISO date" in result.reason


def test_date_field_accepts_iso_format():
    result = validate_screener_answer(FieldType.DATE, "2026-09-01")

    assert result.valid is True


def test_enum_field_rejects_answer_not_in_options():
    result = validate_screener_answer(
        FieldType.ENUM, "Underwater", options=["Remote", "Hybrid", "Onsite"]
    )

    assert result.valid is False
    assert "allowed options" in result.reason


def test_enum_field_accepts_case_insensitive_option_match():
    result = validate_screener_answer(
        FieldType.ENUM, "remote", options=["Remote", "Hybrid", "Onsite"]
    )

    assert result.valid is True


def test_enum_field_without_options_available_does_not_silently_pass():
    result = validate_screener_answer(FieldType.ENUM, "Remote", options=None)

    assert result.valid is False


def test_empty_answer_is_invalid_for_any_field_type():
    result = validate_screener_answer(FieldType.FREE_TEXT, "   ")

    assert result.valid is False
    assert result.reason == "answer is empty"


def test_needs_input_true_when_any_answer_is_a_mismatch():
    questions = [
        {"question": "Years of Go experience?", "field_type": "numeric", "options": []},
        {"question": "Available to start?", "field_type": "date", "options": []},
    ]
    answers = {
        "Years of Go experience?": "5",
        "Available to start?": "whenever works",  # not a valid ISO date
    }

    checks = validate_screener_answers(questions, answers)

    assert needs_input(checks) is True


def test_needs_input_false_when_all_answers_are_valid():
    questions = [
        {"question": "Years of Go experience?", "field_type": "numeric", "options": []},
        {
            "question": "Preferred arrangement?",
            "field_type": "enum",
            "options": ["Remote", "Hybrid"],
        },
    ]
    answers = {
        "Years of Go experience?": "5",
        "Preferred arrangement?": "Remote",
    }

    checks = validate_screener_answers(questions, answers)

    assert needs_input(checks) is False


def test_needs_input_true_when_an_answer_is_missing_entirely():
    questions = [{"question": "Years of Go experience?", "field_type": "numeric", "options": []}]
    answers: dict[str, str] = {}  # question never answered

    checks = validate_screener_answers(questions, answers)

    assert needs_input(checks) is True
