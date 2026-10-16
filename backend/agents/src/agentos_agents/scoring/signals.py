"""Deterministic scoring signals (docs/BACKEND_BUILD_STEPS.md Step 27,
TDD.md §3's Scoring Agent row: "a deterministic keyword/skills-overlap
signal ... and retrieval-relevance stats"). Pure functions, fixed input
always producing the same output — no LLM call, no I/O, nothing
non-deterministic — deliberately, since these are two of the three
signals TDD.md §11.3 says get combined into a calibrated fit score, and a
signal that isn't reproducible can't be usefully calibrated against.

The LLM semantic signal is Step 28, not here — keyword/skills overlap and
retrieval-relevance stats are exactly the two signals that don't need one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class KeywordOverlapResult:
    matched_requirements: list[str]
    missing_requirements: list[str]
    overlap_ratio: float


def keyword_skills_overlap(
    required_skills: list[str], candidate_skills: list[str]
) -> KeywordOverlapResult:
    """For each JD requirement snippet, check whether any of the
    candidate's profile skills appears in it as a whole word/phrase
    (case-insensitive) — required_skills are full phrases ("5+ years of
    experience with Go..."), candidate_skills are short tags ("Go"), so
    this is containment-with-word-boundaries, not equality.

    No required skills listed is treated as fully covered (ratio 1.0),
    not zero — an empty requirement list is a JD data-quality gap, not
    something the candidate should be penalized for.
    """
    if not required_skills:
        return KeywordOverlapResult(
            matched_requirements=[], missing_requirements=[], overlap_ratio=1.0
        )

    matched = []
    missing = []
    for requirement in required_skills:
        if _any_skill_present(candidate_skills, requirement):
            matched.append(requirement)
        else:
            missing.append(requirement)

    return KeywordOverlapResult(
        matched_requirements=matched,
        missing_requirements=missing,
        overlap_ratio=len(matched) / len(required_skills),
    )


def _any_skill_present(candidate_skills: list[str], requirement: str) -> bool:
    requirement_lower = requirement.lower()
    for skill in candidate_skills:
        pattern = r"\b" + re.escape(skill.lower()) + r"\b"
        if re.search(pattern, requirement_lower):
            return True
    return False


@dataclass
class RetrievalRelevanceStats:
    requirement_count: int
    mean_top_similarity: float
    min_top_similarity: float
    covered_ratio: float


def retrieval_relevance_stats(
    requirements: list[dict], threshold: float = 0.5
) -> RetrievalRelevanceStats:
    """Summarizes context.retrieved's per-requirement chunk lists (Step 26's
    output shape: [{"requirement": str, "chunks": [{"similarity": float, ...}]}])
    into stats the heuristic combiner (Step 29) can use — how well-covered
    the JD's requirements are by the candidate's actual profile content,
    not just whether skills text matches.

    A requirement with zero retrieved chunks (profile has nothing close to
    it at all) counts as similarity 0.0 for that requirement, not excluded
    from the average — an uncovered requirement should pull the stats
    down, not be silently skipped.
    """
    if not requirements:
        return RetrievalRelevanceStats(
            requirement_count=0, mean_top_similarity=0.0, min_top_similarity=0.0, covered_ratio=0.0
        )

    top_similarities = [_best_similarity(req) for req in requirements]
    covered = sum(1 for s in top_similarities if s >= threshold)

    return RetrievalRelevanceStats(
        requirement_count=len(requirements),
        mean_top_similarity=sum(top_similarities) / len(top_similarities),
        min_top_similarity=min(top_similarities),
        covered_ratio=covered / len(requirements),
    )


def _best_similarity(requirement_result: dict) -> float:
    chunks = requirement_result.get("chunks") or []
    return max((chunk["similarity"] for chunk in chunks), default=0.0)
