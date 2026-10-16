import pytest

from agentos_agents.scoring.combiner import SCORING_MODEL_VERSION, combine_scores
from agentos_agents.scoring.semantic_signal import SemanticScoreResult
from agentos_agents.scoring.signals import KeywordOverlapResult, RetrievalRelevanceStats


def keyword(ratio: float) -> KeywordOverlapResult:
    return KeywordOverlapResult(
        matched_requirements=[], missing_requirements=[], overlap_ratio=ratio
    )


def retrieval(mean_similarity: float, covered_ratio: float) -> RetrievalRelevanceStats:
    return RetrievalRelevanceStats(
        requirement_count=1,
        mean_top_similarity=mean_similarity,
        min_top_similarity=mean_similarity,
        covered_ratio=covered_ratio,
    )


def semantic(score: int) -> SemanticScoreResult:
    return SemanticScoreResult(score=score, rationale="test")


def test_combine_scores_perfect_signals_score_100():
    breakdown = combine_scores(keyword(1.0), retrieval(1.0, 1.0), semantic(100))

    assert breakdown.score == 100


def test_combine_scores_zero_signals_score_0():
    breakdown = combine_scores(keyword(0.0), retrieval(0.0, 0.0), semantic(0))

    assert breakdown.score == 0


def test_combine_scores_exact_weighted_arithmetic():
    # keyword=0.5*0.3=0.15, retrieval=((0.6+0.4)/2)*0.3=0.15, llm=0.7*0.4=0.28 -> 0.58 -> 58
    breakdown = combine_scores(keyword(0.5), retrieval(0.6, 0.4), semantic(70))

    assert breakdown.score == 58
    assert breakdown.signals["keyword_overlap"].contribution == pytest.approx(0.15)
    assert breakdown.signals["retrieval_relevance"].contribution == pytest.approx(0.15)
    assert breakdown.signals["llm_semantic"].contribution == pytest.approx(0.28)


def test_combine_scores_stamps_scoring_model_version():
    breakdown = combine_scores(keyword(0.5), retrieval(0.5, 0.5), semantic(50))

    assert breakdown.scoring_model_version == SCORING_MODEL_VERSION == "heuristic-v1"


def test_combine_scores_strong_match_scenario_scores_high():
    breakdown = combine_scores(keyword(0.9), retrieval(0.85, 0.8), semantic(88))

    assert breakdown.score >= 80


def test_combine_scores_weak_match_scenario_scores_low():
    breakdown = combine_scores(keyword(0.1), retrieval(0.1, 0.0), semantic(15))

    assert breakdown.score <= 20


def test_combine_scores_mixed_match_scenario_lands_in_the_middle():
    # Strong keyword/retrieval coverage but a lukewarm LLM read shouldn't
    # collapse to either extreme.
    breakdown = combine_scores(keyword(0.8), retrieval(0.75, 0.7), semantic(50))

    assert 40 <= breakdown.score <= 70


def test_score_breakdown_to_json_dict_shape():
    breakdown = combine_scores(keyword(1.0), retrieval(1.0, 1.0), semantic(100))

    data = breakdown.to_json_dict()

    assert data["score"] == 100
    assert data["scoring_model_version"] == "heuristic-v1"
    assert set(data["signals"].keys()) == {"keyword_overlap", "retrieval_relevance", "llm_semantic"}
    assert data["signals"]["keyword_overlap"] == {"value": 1.0, "weight": 0.3, "contribution": 0.3}
