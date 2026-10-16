"""Shared by indexer.py (write path) and retrieval.py (read path) — pgvector's
text input format, not a numpy/pgvector-package dependency (see
python_concepts/13_conftest_and_pgvector_text_format.md).
"""

from __future__ import annotations


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vector) + "]"
