from agentos_agents.scoring.signals import keyword_skills_overlap, retrieval_relevance_stats


def test_keyword_skills_overlap_all_matched():
    result = keyword_skills_overlap(
        required_skills=[
            "5+ years of experience with Go",
            "Strong understanding of distributed systems",
        ],
        candidate_skills=["Go", "distributed systems"],
    )

    assert result.matched_requirements == [
        "5+ years of experience with Go",
        "Strong understanding of distributed systems",
    ]
    assert result.missing_requirements == []
    assert result.overlap_ratio == 1.0


def test_keyword_skills_overlap_none_matched():
    result = keyword_skills_overlap(
        required_skills=["Experience with Kubernetes"],
        candidate_skills=["Go", "Python"],
    )

    assert result.matched_requirements == []
    assert result.missing_requirements == ["Experience with Kubernetes"]
    assert result.overlap_ratio == 0.0


def test_keyword_skills_overlap_partial_match_exact_ratio():
    result = keyword_skills_overlap(
        required_skills=["Go experience", "Kubernetes experience", "PostgreSQL experience"],
        candidate_skills=["Go", "PostgreSQL"],
    )

    assert result.matched_requirements == ["Go experience", "PostgreSQL experience"]
    assert result.missing_requirements == ["Kubernetes experience"]
    assert result.overlap_ratio == 2 / 3


def test_keyword_skills_overlap_no_required_skills_is_fully_covered():
    result = keyword_skills_overlap(required_skills=[], candidate_skills=["Go"])

    assert result.overlap_ratio == 1.0
    assert result.matched_requirements == []
    assert result.missing_requirements == []


def test_keyword_skills_overlap_is_case_insensitive():
    result = keyword_skills_overlap(
        required_skills=["Experience with GO"], candidate_skills=["go"]
    )

    assert result.overlap_ratio == 1.0


def test_keyword_skills_overlap_respects_word_boundaries():
    # "Go" must not match inside "Golang", "Django", or "Mongo" — the
    # deterministic signal is meant to be precise, not a loose substring
    # match that quietly over-counts unrelated skills.
    result = keyword_skills_overlap(
        required_skills=["Experience with Golang", "Django background", "MongoDB knowledge"],
        candidate_skills=["Go"],
    )

    assert result.matched_requirements == []
    assert result.overlap_ratio == 0.0


def test_retrieval_relevance_stats_single_requirement():
    stats = retrieval_relevance_stats(
        requirements=[
            {
                "requirement": "Go experience",
                "chunks": [{"similarity": 0.8}, {"similarity": 0.3}],
            }
        ]
    )

    assert stats.requirement_count == 1
    assert stats.mean_top_similarity == 0.8
    assert stats.min_top_similarity == 0.8
    assert stats.covered_ratio == 1.0


def test_retrieval_relevance_stats_multiple_requirements_exact_values():
    stats = retrieval_relevance_stats(
        requirements=[
            {"requirement": "Go experience", "chunks": [{"similarity": 0.8}]},
            {"requirement": "Kubernetes experience", "chunks": [{"similarity": 0.2}]},
        ],
        threshold=0.5,
    )

    assert stats.requirement_count == 2
    assert stats.mean_top_similarity == 0.5  # (0.8 + 0.2) / 2
    assert stats.min_top_similarity == 0.2
    assert stats.covered_ratio == 0.5  # only the Go requirement clears 0.5


def test_retrieval_relevance_stats_requirement_with_no_chunks_counts_as_zero():
    stats = retrieval_relevance_stats(
        requirements=[
            {"requirement": "Go experience", "chunks": [{"similarity": 0.8}]},
            {"requirement": "Rare skill nobody has", "chunks": []},
        ]
    )

    assert stats.mean_top_similarity == 0.4  # (0.8 + 0.0) / 2
    assert stats.min_top_similarity == 0.0
    assert stats.covered_ratio == 0.5


def test_retrieval_relevance_stats_empty_requirements():
    stats = retrieval_relevance_stats(requirements=[])

    assert stats.requirement_count == 0
    assert stats.mean_top_similarity == 0.0
    assert stats.min_top_similarity == 0.0
    assert stats.covered_ratio == 0.0


def test_retrieval_relevance_stats_threshold_boundary_is_inclusive():
    stats = retrieval_relevance_stats(
        requirements=[{"requirement": "Go experience", "chunks": [{"similarity": 0.5}]}],
        threshold=0.5,
    )

    assert stats.covered_ratio == 1.0  # similarity == threshold counts as covered
