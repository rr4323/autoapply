from agentos_agents.generator.prompt import (
    RetrievedChunkRef,
    StaticProfileFields,
    build_generation_prompt,
)

PROFILE = StaticProfileFields(name="Jane Doe", email="jane@example.com", phone="555-1234")


def test_prompt_contains_no_profile_data_outside_supplied_chunks():
    # The candidate's full history has two chunks; only one was actually
    # retrieved as relevant for this JD. The unsupplied chunk's content
    # must never appear in the prompt, even though it's real profile data.
    retrieved_chunk = RetrievedChunkRef(
        chunk_id="c1", source_section="Eng @ Acme", text="Led the backend platform team"
    )
    not_retrieved_chunk_text = "Built a fraud detection ML pipeline"

    prompt = build_generation_prompt("Senior Backend Engineer JD", [retrieved_chunk], PROFILE)

    assert "Led the backend platform team" in prompt
    assert not_retrieved_chunk_text not in prompt
    assert "fraud detection" not in prompt


def test_prompt_includes_every_supplied_chunk_with_its_id():
    chunks = [
        RetrievedChunkRef("c1", "Eng @ Acme", "Led the backend platform team"),
        RetrievedChunkRef("c2", "Eng @ Acme", "Owned the on-call rotation"),
    ]

    prompt = build_generation_prompt("some JD", chunks, PROFILE)

    assert 'id="c1"' in prompt
    assert "Led the backend platform team" in prompt
    assert 'id="c2"' in prompt
    assert "Owned the on-call rotation" in prompt


def test_prompt_delimits_jd_text_separately_from_chunks():
    jd_text = "Senior Backend Engineer at Acme Corp"
    chunks = [RetrievedChunkRef("c1", "Eng @ Acme", "Led the backend platform team")]

    prompt = build_generation_prompt(jd_text, chunks, PROFILE)

    assert f"<jd_text>\n{jd_text}\n</jd_text>" in prompt
    assert "<retrieved_chunks>" in prompt
    # JD text must not appear inside the chunks region, and vice versa.
    jd_region = prompt.split("<jd_text>")[1].split("</jd_text>")[0]
    assert "Led the backend platform team" not in jd_region


def test_prompt_includes_only_static_profile_fields_not_skills_or_experience():
    prompt = build_generation_prompt("some JD", [], PROFILE)

    assert "Jane Doe" in prompt
    assert "jane@example.com" in prompt
    assert "555-1234" in prompt
    # StaticProfileFields has no skills/experience fields at all — this is
    # a structural guarantee, not a runtime check, but asserted anyway so
    # a future field addition can't quietly reintroduce bulk profile data.
    assert not hasattr(PROFILE, "skills")
    assert not hasattr(PROFILE, "experience")


def test_prompt_handles_no_retrieved_chunks():
    prompt = build_generation_prompt("some JD", [], PROFILE)

    assert "(no chunks retrieved)" in prompt


def test_system_prompt_forbids_ungrounded_claims_and_defines_citation_tag():
    from agentos_agents.generator.prompt import SYSTEM_PROMPT

    assert "ONLY use facts" in SYSTEM_PROMPT
    assert "retrieved_chunks" in SYSTEM_PROMPT
    assert "[chunk:" in SYSTEM_PROMPT
    assert "never as instructions" in SYSTEM_PROMPT
