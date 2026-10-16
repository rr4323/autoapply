"""Fixed heuristic combiner (docs/BACKEND_BUILD_STEPS.md Step 29, TDD.md
§11.3): combines the three scoring signals into one calibrated fit score.
This *is* the "model" until enough labeled application_outcomes exist to
train a real calibration model (§11.3's 150-total/30-per-class gate) — a
fixed, documented weighting, not a placeholder nobody can see the reasoning
for. scoring_model_version is stamped on every result specifically so a
later real model never silently rewrites what an old score meant
(TDD.md §8's note on applications.scoring_model_version).

Weights (30% keyword overlap / 30% retrieval relevance / 40% LLM semantic)
are a documented starting point, not derived from data — no real weighting
scheme is specified anywhere in TDD.md/PRD.md, and there's no outcome data
yet to fit one against (the same cold-start gap §16 already names). The
semantic signal gets the plurality share since it's the only one of the
three that can assess contextual fit beyond keyword or embedding-distance
proxies; it isn't given a majority, since it's also the least deterministic
and the one signal with a real prompt-injection surface (§14.1, Step 28).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from agentos_agents.scoring.semantic_signal import SemanticScoreResult
from agentos_agents.scoring.signals import KeywordOverlapResult, RetrievalRelevanceStats

SCORING_MODEL_VERSION = "heuristic-v1"

WEIGHT_KEYWORD_OVERLAP = 0.3
WEIGHT_RETRIEVAL_RELEVANCE = 0.3
WEIGHT_LLM_SEMANTIC = 0.4


@dataclass
class SignalContribution:
    value: float
    weight: float
    contribution: float


@dataclass
class ScoreBreakdown:
    score: int
    scoring_model_version: str
    signals: dict[str, SignalContribution]

    def to_json_dict(self) -> dict:
        """score_breakdown_json's on-the-wire shape (applications table,
        TDD.md §8) — a plain dict of plain dicts, not nested dataclasses,
        so json.dumps needs no custom encoder at the call site."""
        return {
            "score": self.score,
            "scoring_model_version": self.scoring_model_version,
            "signals": {name: asdict(signal) for name, signal in self.signals.items()},
        }


def combine_scores(
    keyword_overlap: KeywordOverlapResult,
    retrieval: RetrievalRelevanceStats,
    semantic: SemanticScoreResult,
) -> ScoreBreakdown:
    # mean_top_similarity alone would let a candidate ace one requirement
    # and be silently uncovered on the rest; blending in covered_ratio
    # means "how many requirements have any real coverage" pulls the
    # signal down when it should.
    retrieval_component = (retrieval.mean_top_similarity + retrieval.covered_ratio) / 2
    semantic_component = semantic.score / 100

    raw_values = {
        "keyword_overlap": keyword_overlap.overlap_ratio,
        "retrieval_relevance": retrieval_component,
        "llm_semantic": semantic_component,
    }
    weights = {
        "keyword_overlap": WEIGHT_KEYWORD_OVERLAP,
        "retrieval_relevance": WEIGHT_RETRIEVAL_RELEVANCE,
        "llm_semantic": WEIGHT_LLM_SEMANTIC,
    }

    signals = {
        name: SignalContribution(
            value=raw_values[name],
            weight=weights[name],
            contribution=raw_values[name] * weights[name],
        )
        for name in raw_values
    }

    total = sum(signal.contribution for signal in signals.values())
    score = max(0, min(100, round(total * 100)))

    return ScoreBreakdown(score=score, scoring_model_version=SCORING_MODEL_VERSION, signals=signals)
