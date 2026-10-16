"""Resume chunker (docs/BACKEND_BUILD_STEPS.md Step 23, TDD.md §6.1).

Splits profiles.experience_json into chunks aligned with experience-entry/
bullet boundaries, never a fixed token window — a token window can cut a
bullet mid-sentence, producing a chunk that isn't "a coherent, citable
fact" (§6.1's own phrase), which is exactly what the Generator Agent's
per-claim citation check (§6.3) needs each chunk to be.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, TypeAdapter, ValidationError


class ExperienceEntry(BaseModel):
    """Mirrors backend/api/internal/handlers/profile.go's experienceEntry —
    the Go API is what writes profiles.experience_json, so this has to
    match its JSON shape exactly, not just be "close enough."
    """

    id: str
    company: str
    title: str
    start_date: str
    end_date: str | None = None
    bullets: list[str] = []


_ExperienceList = TypeAdapter(list[ExperienceEntry])


class ChunkingError(Exception):
    """Raised when experience_json doesn't match the profiles.experience_json
    contract — either invalid JSON or a shape pydantic can't validate.
    """


@dataclass
class Chunk:
    source_section: str
    text: str


def chunk_experience(experience_json: str | bytes) -> list[Chunk]:
    try:
        entries = _ExperienceList.validate_json(experience_json)
    except ValidationError as e:
        raise ChunkingError(f"experience_json does not match the expected shape: {e}") from e

    chunks: list[Chunk] = []
    for entry in entries:
        section = _section_label(entry)
        bullets = [b.strip() for b in entry.bullets if b.strip()]

        if not bullets:
            # An entry with no bullets yet (company/title filled in, not
            # detailed) would otherwise be invisible to retrieval entirely —
            # one fallback chunk keeps it citable instead of silently
            # dropped.
            chunks.append(Chunk(source_section=section, text=_fallback_summary(entry)))
            continue

        for bullet in bullets:
            chunks.append(Chunk(source_section=section, text=bullet))

    return chunks


def _section_label(entry: ExperienceEntry) -> str:
    return f"{entry.title} @ {entry.company}"


def _fallback_summary(entry: ExperienceEntry) -> str:
    end = entry.end_date or "present"
    return f"{entry.title} at {entry.company} ({entry.start_date} - {end})"
