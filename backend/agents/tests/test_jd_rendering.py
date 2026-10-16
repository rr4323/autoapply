from agentos_agents.scoring.jd_rendering import render_jd_text


def test_render_jd_text_includes_all_present_fields():
    text = render_jd_text(
        {
            "title": "Senior Backend Engineer",
            "company": "Acme Corp",
            "required_skills": ["Go", "Distributed systems"],
            "responsibilities": ["Own the on-call rotation"],
        }
    )

    assert "Title: Senior Backend Engineer" in text
    assert "Company: Acme Corp" in text
    assert "- Go" in text
    assert "- Distributed systems" in text
    assert "- Own the on-call rotation" in text


def test_render_jd_text_omits_missing_fields():
    text = render_jd_text({"title": "Senior Backend Engineer"})

    assert "Title: Senior Backend Engineer" in text
    assert "Company:" not in text
    assert "Requirements:" not in text


def test_render_jd_text_handles_completely_empty_input():
    assert render_jd_text({}) == "(no JD details available)"
