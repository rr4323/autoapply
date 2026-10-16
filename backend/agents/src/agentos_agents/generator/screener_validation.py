"""Screener-answer type/length validation (docs/BACKEND_BUILD_STEPS.md
Step 37, TDD.md §6.5): a Generator-drafted answer is checked against the
field type Step 20's Scraper Agent inferred, and a length cap — a
type/length mismatch is a *shape* problem, distinct from Step 35's
citation check, which covers whether the *content* is true. A mismatch
routes to needs_input rather than failing outright, reusing the same
batched-review path PRD §5.1 step 8 already defines for fields the
pipeline can't resolve at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from agentos_agents.scraper.screener import FieldType

# "a sane length" (TDD.md §6.5's own phrase) — a documented starting
# point, not a calibrated number; no golden dataset exists yet to derive
# one from, same cold-start gap as the scoring combiner's weights (Step 29).
MAX_FREE_TEXT_LENGTH = 500


@dataclass
class ValidationResult:
    valid: bool
    reason: str | None = None


def validate_screener_answer(
    field_type: FieldType, answer: str, options: list[str] | None = None
) -> ValidationResult:
    answer = answer.strip()
    if not answer:
        return ValidationResult(valid=False, reason="answer is empty")

    if field_type == FieldType.FREE_TEXT:
        return _validate_free_text(answer)
    if field_type == FieldType.YES_NO:
        return _validate_yes_no(answer)
    if field_type == FieldType.NUMERIC:
        return _validate_numeric(answer)
    if field_type == FieldType.DATE:
        return _validate_date(answer)
    if field_type == FieldType.ENUM:
        return _validate_enum(answer, options or [])

    return ValidationResult(valid=False, reason=f"unknown field_type {field_type!r}")


def _validate_free_text(answer: str) -> ValidationResult:
    if len(answer) > MAX_FREE_TEXT_LENGTH:
        return ValidationResult(
            valid=False, reason=f"answer exceeds {MAX_FREE_TEXT_LENGTH} characters"
        )
    return ValidationResult(valid=True)


def _validate_yes_no(answer: str) -> ValidationResult:
    if answer.lower() not in ("yes", "no"):
        return ValidationResult(valid=False, reason="answer is not yes/no")
    return ValidationResult(valid=True)


def _validate_numeric(answer: str) -> ValidationResult:
    try:
        float(answer)
    except ValueError:
        return ValidationResult(valid=False, reason="answer is not numeric")
    return ValidationResult(valid=True)


def _validate_date(answer: str) -> ValidationResult:
    try:
        date.fromisoformat(answer)
    except ValueError:
        return ValidationResult(valid=False, reason="answer is not a valid ISO date (YYYY-MM-DD)")
    return ValidationResult(valid=True)


def _validate_enum(answer: str, options: list[str]) -> ValidationResult:
    if not options:
        # No option list to check against (e.g. older extracted data) —
        # can't confirm shape correctness, so this doesn't silently pass.
        return ValidationResult(
            valid=False, reason="no allowed options available to validate against"
        )
    allowed_lower = {o.lower() for o in options}
    if answer.lower() not in allowed_lower:
        return ValidationResult(
            valid=False, reason=f"answer is not one of the allowed options: {options}"
        )
    return ValidationResult(valid=True)


@dataclass
class ScreenerAnswerCheck:
    question: str
    answer: str
    result: ValidationResult


def validate_screener_answers(
    questions: list[dict], answers: dict[str, str]
) -> list[ScreenerAnswerCheck]:
    checks = []
    for q in questions:
        answer = answers.get(q["question"], "")
        field_type = FieldType(q["field_type"])
        result = validate_screener_answer(field_type, answer, q.get("options"))
        checks.append(ScreenerAnswerCheck(question=q["question"], answer=answer, result=result))
    return checks


def needs_input(checks: list[ScreenerAnswerCheck]) -> bool:
    """True if any answer failed validation — the whole document routes
    to needs_input on a single mismatch, not just the offending field,
    matching PRD §5.1 step 8's batched-review behavior.
    """
    return any(not c.result.valid for c in checks)
