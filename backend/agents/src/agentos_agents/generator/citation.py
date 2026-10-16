"""Per-claim chunk_id tagging + the cheap non-LLM citation check
(docs/BACKEND_BUILD_STEPS.md Step 35, TDD.md §6.3): "a post-generation
pass checks that every tagged claim's key terms actually appear in the
cited chunk." Deliberately not an LLM call — this is the cheap first-pass
filter §10's groundedness evaluation later layers a Ragas faithfulness
judge on top of, mirroring the same deterministic-then-LLM shape already
used for scoring (Step 27/28) and the guardrail scan (Step 36).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agentos_agents.generator.prompt import RetrievedChunkRef

# Matches the [chunk:<id>] tag format prompt.py's SYSTEM_PROMPT asks the
# LLM to produce, capturing the claim text immediately preceding it.
_CITATION_TAG_PATTERN = re.compile(r"(.*?)\[chunk:([^\]]+)\]", re.DOTALL)

_STOPWORDS = {
    "a", "an", "the", "of", "for", "and", "or", "at", "in", "on", "to",
    "with", "is", "was", "were", "be", "been", "as", "by", "from", "that",
}

# Fraction of a claim's key terms that must appear in the cited chunk for
# the claim to count as grounded — a documented starting point (no golden
# dataset exists yet to calibrate against, same cold-start gap as the
# scoring combiner's weights, Step 29), not a value derived from data.
DEFAULT_GROUNDED_THRESHOLD = 0.6


@dataclass
class TaggedClaim:
    text: str
    chunk_id: str


@dataclass
class CitationCheckResult:
    claim: str
    chunk_id: str
    grounded: bool
    matched_key_terms: list[str]
    missing_key_terms: list[str]


@dataclass
class GroundednessReport:
    results: list[CitationCheckResult]

    @property
    def all_grounded(self) -> bool:
        return all(r.grounded for r in self.results)

    @property
    def ungrounded_claims(self) -> list[CitationCheckResult]:
        return [r for r in self.results if not r.grounded]


def parse_tagged_claims(generated_text: str) -> list[TaggedClaim]:
    claims = []
    for match in _CITATION_TAG_PATTERN.finditer(generated_text):
        text = match.group(1).strip()
        chunk_id = match.group(2).strip()
        if text:
            claims.append(TaggedClaim(text=text, chunk_id=chunk_id))
    return claims


def check_document_groundedness(
    generated_text: str,
    chunks: list[RetrievedChunkRef],
    grounded_threshold: float = DEFAULT_GROUNDED_THRESHOLD,
) -> GroundednessReport:
    chunks_by_id = {c.chunk_id: c for c in chunks}
    claims = parse_tagged_claims(generated_text)
    results = [_check_claim(claim, chunks_by_id, grounded_threshold) for claim in claims]
    return GroundednessReport(results=results)


def _check_claim(
    claim: TaggedClaim, chunks_by_id: dict[str, RetrievedChunkRef], grounded_threshold: float
) -> CitationCheckResult:
    key_terms = _key_terms(claim.text)

    chunk = chunks_by_id.get(claim.chunk_id)
    if chunk is None:
        # A citation pointing at a chunk_id that was never actually
        # supplied is exactly as ungrounded as a claim with no matching
        # terms — the LLM can't cite its way into a chunk it wasn't given.
        return CitationCheckResult(claim.text, claim.chunk_id, False, [], key_terms)

    if not key_terms:
        # No meaningful terms to check at all — treated conservatively as
        # ungrounded rather than vacuously true.
        return CitationCheckResult(claim.text, claim.chunk_id, False, [], [])

    chunk_text_lower = chunk.text.lower()
    matched = [t for t in key_terms if _word_present(t, chunk_text_lower)]
    missing = [t for t in key_terms if t not in matched]

    grounded = (len(matched) / len(key_terms)) >= grounded_threshold
    return CitationCheckResult(claim.text, claim.chunk_id, grounded, matched, missing)


def _key_terms(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    seen: dict[str, None] = {}
    for word in words:
        if len(word) >= 2 and word not in _STOPWORDS:
            seen.setdefault(word, None)
    return list(seen)


def _word_present(term: str, text_lower: str) -> bool:
    return re.search(r"\b" + re.escape(term) + r"\b", text_lower) is not None
