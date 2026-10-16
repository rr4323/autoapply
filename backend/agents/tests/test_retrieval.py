from agentos_agents.retriever.retrieval import SimilarApplication, _rank_by_title_overlap


def app(role_title: str, application_id: str = "id") -> SimilarApplication:
    return SimilarApplication(
        application_id=application_id,
        role_title=role_title,
        company=None,
        resume_match_score=None,
        jd_fit_score=None,
        outcome=None,
    )


def test_rank_by_title_overlap_orders_by_shared_word_count():
    candidates = [
        app("Marketing Manager", "no-overlap"),
        app("Senior Backend Engineer", "full-overlap"),
        app("Backend Engineer", "partial-overlap"),
    ]

    ranked = _rank_by_title_overlap("Senior Backend Engineer", candidates)

    assert [c.application_id for c in ranked] == ["full-overlap", "partial-overlap"]


def test_rank_by_title_overlap_excludes_titles_with_zero_overlap():
    candidates = [app("Marketing Manager"), app("Product Designer")]

    ranked = _rank_by_title_overlap("Senior Backend Engineer", candidates)

    assert ranked == []


def test_rank_by_title_overlap_ignores_stopwords():
    candidates = [app("Engineer of the Year")]

    # "of"/"the" shouldn't count as a real match on their own.
    ranked = _rank_by_title_overlap("Manager of the Board", candidates)

    assert ranked == []
