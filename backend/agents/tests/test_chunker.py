import json

import pytest

from agentos_agents.retriever.chunker import ChunkingError, chunk_experience

BASE_ENTRY = {
    "id": "e1",
    "company": "Acme Corp",
    "title": "Senior Backend Engineer",
    "start_date": "2020-01",
    "end_date": None,
    "bullets": [],
}


def test_chunk_experience_empty_list_returns_no_chunks():
    assert chunk_experience(json.dumps([])) == []


def test_chunk_experience_entry_without_bullets_falls_back_to_summary():
    entry = {**BASE_ENTRY, "bullets": []}

    chunks = chunk_experience(json.dumps([entry]))

    assert len(chunks) == 1
    assert chunks[0].source_section == "Senior Backend Engineer @ Acme Corp"
    assert chunks[0].text == "Senior Backend Engineer at Acme Corp (2020-01 - present)"


def test_chunk_experience_blank_bullets_are_filtered_not_kept_as_empty_chunks():
    entry = {**BASE_ENTRY, "bullets": ["   ", "", "Led the platform team"]}

    chunks = chunk_experience(json.dumps([entry]))

    assert len(chunks) == 1
    assert chunks[0].text == "Led the platform team"


def test_chunk_experience_very_short_bullet_becomes_its_own_chunk():
    entry = {**BASE_ENTRY, "bullets": ["Led team."]}

    chunks = chunk_experience(json.dumps([entry]))

    assert len(chunks) == 1
    assert chunks[0].text == "Led team."


def test_chunk_experience_very_long_bullet_is_never_split():
    long_bullet = "Scaled the payments platform to handle 10x traffic. " * 200
    entry = {**BASE_ENTRY, "bullets": [long_bullet.strip()]}

    chunks = chunk_experience(json.dumps([entry]))

    assert len(chunks) == 1
    assert chunks[0].text == long_bullet.strip()  # whole bullet, no token-window truncation


def test_chunk_experience_multiple_bullets_become_separate_chunks_same_section():
    entry = {**BASE_ENTRY, "bullets": ["Led the platform team", "Owned the on-call rotation"]}

    chunks = chunk_experience(json.dumps([entry]))

    assert [c.text for c in chunks] == ["Led the platform team", "Owned the on-call rotation"]
    assert all(c.source_section == "Senior Backend Engineer @ Acme Corp" for c in chunks)


def test_chunk_experience_rejects_invalid_json_syntax():
    with pytest.raises(ChunkingError):
        chunk_experience("{not valid json")


def test_chunk_experience_rejects_wrong_shape():
    # A dict, not a list — profiles.experience_json is always an array.
    with pytest.raises(ChunkingError):
        chunk_experience(json.dumps({"company": "Acme Corp"}))


def test_chunk_experience_rejects_entry_missing_required_fields():
    with pytest.raises(ChunkingError):
        chunk_experience(json.dumps([{"company": "Acme Corp"}]))  # missing id/title/start_date
