import json

from agentos_agents.demo_clients import (
    DemoDomAnalysisLLMClient,
    DemoEmbeddingClient,
    DemoGeneratorLLMClient,
    DemoScoringLLMClient,
)
from agentos_agents.generator.guardrail import STAGE2_SYSTEM_PROMPT
from agentos_agents.generator.prompt import SYSTEM_PROMPT as GENERATION_SYSTEM_PROMPT
from agentos_agents.generator.screener_answers import SCREENER_ANSWER_SYSTEM_PROMPT
from agentos_agents.generator.screener_validation import FieldType, validate_screener_answer
from agentos_agents.scraper.screener import FieldType as ScreenerFieldType


async def test_demo_embedding_client_produces_1536_dim_vectors_that_differ():
    client = DemoEmbeddingClient()

    vectors = await client.embed_batch(["Go backend engineer", "Fashion design specialist"])

    assert len(vectors) == 2
    assert all(len(v) == 1536 for v in vectors)
    assert vectors[0] != vectors[1]
    assert sum(vectors[0]) > 0  # "go"/"backend"/"engineer" hit the vocab
    assert sum(vectors[1]) == 0  # nothing in "fashion design specialist" matches


async def test_demo_scoring_client_returns_valid_score_json():
    client = DemoScoringLLMClient()

    raw = await client.complete("any system prompt", "any user prompt")
    data = json.loads(raw)

    assert 0 <= data["score"] <= 100


async def test_demo_generator_client_drafts_grounded_section_with_citations():
    client = DemoGeneratorLLMClient()
    user_prompt = (
        'Candidate: Demo Candidate | demo@example.com\n\n<jd_text>\nSome JD\n</jd_text>\n\n'
        '<retrieved_chunks>\n<chunk id="abc-123" section="Eng @ Acme">\nLed the platform team'
        "\n</chunk>\n</retrieved_chunks>\n\nDraft the resume bullets..."
    )

    raw = await client.complete(GENERATION_SYSTEM_PROMPT, user_prompt)

    assert "Led the platform team" in raw
    assert "[chunk:abc-123]" in raw


async def test_demo_generator_client_stage2_judge_returns_valid_json():
    client = DemoGeneratorLLMClient()

    raw = await client.complete(STAGE2_SYSTEM_PROMPT, "Flagged emails: []\nFlagged URLs: []")
    data = json.loads(raw)

    assert data["injection"] is False


async def test_demo_generator_client_drafts_valid_answers_per_field_type():
    client = DemoGeneratorLLMClient()

    cases = [
        ("numeric", "Question (field_type=numeric): Years of Go experience?"),
        ("yes_no", "Question (field_type=yes_no): Authorized to work here?"),
        ("date", "Question (field_type=date): Available from?"),
        (
            "enum",
            "Question (field_type=enum): Preferred arrangement? "
            "Allowed options: ['Remote', 'Hybrid', 'Onsite'].",
        ),
        ("free_text", "Question (field_type=free_text): Why this role?"),
    ]
    for field_type, user_prompt in cases:
        raw = await client.complete(SCREENER_ANSWER_SYSTEM_PROMPT, user_prompt)
        result = validate_screener_answer(
            FieldType(field_type), raw, options=["Remote", "Hybrid", "Onsite"]
        )
        assert result.valid is True, f"{field_type} answer {raw!r} failed: {result.reason}"


async def test_demo_dom_analysis_client_returns_the_real_fixture_field_map():
    client = DemoDomAnalysisLLMClient()

    raw = await client.complete("any system prompt", "any user prompt")
    data = json.loads(raw)

    assert data["first_name"] == "#first_name"
    assert data["Are you legally authorized to work in the country of this job?"] == "#q_auth"


def test_field_type_enum_names_match_between_modules():
    # demo_clients dispatches on field_type strings that must match
    # scraper.screener.FieldType's actual values, or a real answer would
    # be validated against the wrong shape.
    assert {t.value for t in ScreenerFieldType} == {t.value for t in FieldType}
