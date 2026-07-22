"""Research retrieval against research_documents (pgvector cosine distance).

research_documents is deliberately seeded EMPTY (see the header comment in
db/migrations/0002_seed_rubric_v1.sql) -- we chose not to fabricate
placeholder research citations/URLs, since that would be dishonest. This
module still implements real retrieval plumbing so it activates automatically
the moment documents exist; until then it correctly returns [].

The embedding is a fixed-seed hashing trick, not a real ML model -- good
enough to exercise the pgvector query shape without pulling in
torch/sentence-transformers for a beta whose research table is empty anyway.
"""
from __future__ import annotations

import hashlib
import math

EMBEDDING_DIM = 384


def embed_text(text: str) -> list[float]:
    """Deterministic bag-of-hashed-tokens embedding, L2-normalized."""
    vector = [0.0] * EMBEDDING_DIM
    tokens = text.lower().split()
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [v / norm for v in vector]
    return vector


def _vector_literal(vector: list[float]) -> str:
    # Passed as text and cast with ::vector in SQL so this works without the
    # separate `pgvector` python package (not in requirements.txt) registering
    # a type adapter -- psycopg only needs to adapt a plain string here.
    return "[" + ",".join(f"{v:.6f}" for v in vector) + "]"


def retrieve_research(query_text: str, top_k: int = 3, conn=None) -> list[dict]:
    if conn is None or not query_text or not query_text.strip():
        return []
    embedding_literal = _vector_literal(embed_text(query_text))
    try:
        # This runs inside the single transaction the scoring pipeline's
        # caller owns (see app/main.py's job-attempt contract) -- a bare
        # conn.execute() failure would poison that whole transaction for
        # every later statement (score_items/recommendations inserts
        # included). conn.transaction() opens a SAVEPOINT here instead, so a
        # failure rolls back only this query and the outer transaction stays
        # healthy for assemble.assemble_and_publish().
        with conn.transaction():
            rows = conn.execute(
                """
                SELECT id, source_url, publisher, claim, audience, confidence,
                       embedding <=> %s::vector AS distance
                FROM research_documents
                WHERE embedding IS NOT NULL
                ORDER BY distance ASC
                LIMIT %s
                """,
                (embedding_literal, top_k),
            ).fetchall()
    except Exception:
        # Research retrieval is a pure enrichment step; any failure (missing
        # table, bad connection state, etc.) must never break recommendations.
        return []
    return [dict(r) for r in rows]
