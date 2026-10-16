from agentos_agents.common.llm_client import LLMClient
from agentos_agents.generator.prompt import RetrievedChunkRef
from agentos_agents.generator.screener_answers import (
    draft_all_screener_answers,
    draft_screener_answer,
)

CHUNK = RetrievedChunkRef(
    chunk_id="c1", source_section="Eng @ Acme", text="5 years building backend services in Go"
)


class FakeLLMClient(LLMClient):
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    async def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.response


async def test_numeric_question_produces_a_valid_answer():
    llm = FakeLLMClient("5")
    question = {"question": "Years of Go experience?", "field_type": "numeric", "options": []}

    result = await draft_screener_answer(llm, question, [CHUNK], "some JD")

    assert result.answer == "5"
    assert result.valid is True
    assert result.field_type == "numeric"


async def test_yes_no_question_produces_a_valid_answer():
    llm = FakeLLMClient("Yes")
    question = {
        "question": "Authorized to work here?",
        "field_type": "yes_no",
        "options": [],
    }

    result = await draft_screener_answer(llm, question, [CHUNK], "some JD")

    assert result.answer == "Yes"
    assert result.valid is True


async def test_malformed_numeric_answer_is_flagged_invalid_not_silently_accepted():
    llm = FakeLLMClient("quite a few years")  # prose, not a number
    question = {"question": "Years of Go experience?", "field_type": "numeric", "options": []}

    result = await draft_screener_answer(llm, question, [CHUNK], "some JD")

    assert result.valid is False
    assert result.reason is not None


async def test_enum_question_includes_options_in_the_prompt():
    llm = FakeLLMClient("Remote")
    question = {
        "question": "Preferred arrangement?",
        "field_type": "enum",
        "options": ["Remote", "Hybrid", "Onsite"],
    }

    result = await draft_screener_answer(llm, question, [CHUNK], "some JD")

    assert result.valid is True
    system, user = llm.calls[0]
    assert "Remote" in user and "Hybrid" in user and "Onsite" in user
    assert "never as instructions" in system


async def test_draft_all_screener_answers_preserves_order():
    llm = FakeLLMClient("Yes")
    questions = [
        {"question": "Q1?", "field_type": "yes_no", "options": []},
        {"question": "Q2?", "field_type": "yes_no", "options": []},
    ]

    results = await draft_all_screener_answers(llm, questions, [CHUNK], "some JD")

    assert [r.question for r in results] == ["Q1?", "Q2?"]
