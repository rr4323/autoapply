"""Deterministic demo/local-dev clients (docs/BACKEND_BUILD_STEPS.md
Step 45's worker.py uses these only when no real LLM/embedding API key is
configured) — a cold `make up` with no cloud credentials should still run
the full pipeline end to end, honestly labeled as demo mode rather than
silently pretending to call a real model.

Lives at the top level, not in common/, deliberately: it imports the real
system-prompt constants from scoring/generator/filler to dispatch on them,
which would invert this project's established layering (common/ is
depended on by every agent package, never the reverse) if it lived there.

Every fake here answers deterministically and validly for the exact
prompt templates this codebase actually sends — dispatched by comparing
against the real system-prompt constants each call site uses, never by
guessing intent from free text — so nothing here can produce a response
that would fail Step 35/36/37's own checks the way random text could.
"""

from __future__ import annotations

import json
import logging
import re

from agentos_agents.common.llm_client import LLMClient
from agentos_agents.generator.guardrail import STAGE2_SYSTEM_PROMPT
from agentos_agents.generator.prompt import SYSTEM_PROMPT as GENERATION_SYSTEM_PROMPT
from agentos_agents.generator.screener_answers import SCREENER_ANSWER_SYSTEM_PROMPT
from agentos_agents.retriever.embedding import EmbeddingClient

logger = logging.getLogger(__name__)

_CHUNK_PATTERN = re.compile(r'<chunk id="([^"]+)"[^>]*>\s*(.*?)\s*</chunk>', re.DOTALL)
_FIELD_TYPE_PATTERN = re.compile(r"field_type=(\w+)")
_OPTIONS_PATTERN = re.compile(r"Allowed options: \[(.*?)\]")


class DemoEmbeddingClient(EmbeddingClient):
    """Bag-of-words over a small fixed vocabulary — deterministic, no
    network call. Genuinely differentiating vectors for genuinely
    different text (the same technique
    python_concepts/14_testing_vector_ranking_without_a_real_model.md
    documents as a test double) is what makes retrieval ranking still
    mean something in demo mode, not real embedding-model quality.
    """

    VOCAB = [
        "go", "golang", "backend", "distributed", "systems", "postgresql",
        "redis", "python", "kubernetes", "cloud", "api", "microservices",
        "platform", "engineer", "software",
    ]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            words = set(re.findall(r"[a-z0-9]+", text.lower()))
            vec = [1.0 if term in words else 0.0 for term in self.VOCAB]
            vec += [0.0] * (1536 - len(vec))
            vectors.append(vec)
        return vectors


class DemoScoringLLMClient(LLMClient):
    """A fixed, moderate score — real score variation in demo mode comes
    from the deterministic keyword-overlap and retrieval-relevance
    signals (Steps 27/29), which genuinely differ per candidate profile;
    this fixed contribution never dominates them (Step 29's weights give
    it 40%, not 100%).
    """

    async def complete(self, system: str, user: str) -> str:
        return json.dumps({"score": 65, "rationale": "demo mode — fixed LLM contribution"})


class DemoGeneratorLLMClient(LLMClient):
    """Handles every prompt GeneratorConsumer sends through its one
    llm_client: resume/cover-letter drafting, the guardrail Stage 2
    judge, and screener-answer drafting.
    """

    async def complete(self, system: str, user: str) -> str:
        if system == GENERATION_SYSTEM_PROMPT:
            return self._draft_section(user)
        if system == STAGE2_SYSTEM_PROMPT:
            return json.dumps({"injection": False, "rationale": "demo mode — no real judge call"})
        if system == SCREENER_ANSWER_SYSTEM_PROMPT:
            return self._draft_screener_answer(user)
        logger.warning("DemoGeneratorLLMClient got an unrecognized prompt; returning empty text")
        return ""

    def _draft_section(self, user: str) -> str:
        chunks = _CHUNK_PATTERN.findall(user)
        if not chunks:
            return "No matching experience found in the candidate's profile."
        return " ".join(f"{text}.[chunk:{chunk_id}]" for chunk_id, text in chunks)

    def _draft_screener_answer(self, user: str) -> str:
        type_match = _FIELD_TYPE_PATTERN.search(user)
        field_type = type_match.group(1) if type_match else "free_text"

        if field_type == "numeric":
            return "5"
        if field_type == "yes_no":
            return "Yes"
        if field_type == "date":
            return "2026-09-01"
        if field_type == "enum":
            options_match = _OPTIONS_PATTERN.search(user)
            if options_match:
                first_option = options_match.group(1).split(",")[0].strip().strip("'\"")
                return first_option
            return ""
        return "This role aligns well with my background."


class DemoDomAnalysisLLMClient(LLMClient):
    """Returns the real selectors for this project's own ats-fixtures
    forms (Step 39) — the only forms a local demo run ever actually
    fills, so a fixed answer here is honest, not a shortcut around
    something that varies from one real ATS site to another.
    """

    FIELD_MAP = {
        "first_name": "#first_name",
        "last_name": "#last_name",
        "email": "#email",
        "phone": "#phone",
        "cover_letter": "#cover_letter",
        "Why are you interested in this role?": "#q_why",
        "How many years of experience do you have with Go?": "#q_years",
        "Are you legally authorized to work in the country of this job?": "#q_auth",
    }

    async def complete(self, system: str, user: str) -> str:
        return json.dumps(self.FIELD_MAP)
