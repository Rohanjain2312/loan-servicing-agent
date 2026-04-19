"""
rag_query_tool.py — Hybrid RAG search combining pgvector cosine similarity (semantic)
and PostgreSQL full-text search (keyword), with keyword-first ranking.
No DELETE statements anywhere in this file.
"""

from langchain_core.tools import tool
import os
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
from openai import OpenAI
from dotenv import load_dotenv
from typing import Any

load_dotenv()

EMBEDDING_MODEL = "text-embedding-3-small"


@tool
def rag_query_tool(
    deal_id: int,
    query: str,
    top_k: int = 5,
) -> dict[str, Any]:
    """
    Hybrid RAG search over ca_embeddings for a specific deal.

    Combines:
      - Semantic search via pgvector cosine similarity (text-embedding-3-small)
      - Full-text keyword search via PostgreSQL ts_rank / plainto_tsquery

    Ranking strategy (keyword-first):
      1. Chunks matched by keyword search are ranked first (sorted by semantic_score desc).
      2. Chunks matched only by semantic search follow (sorted by semantic_score desc).

    Args:
        deal_id: Mandatory deal identifier — search is scoped to this deal only.
        query: Natural language query string.
        top_k: Number of chunks to return (default 5).

    Returns:
        Dict with keys:
            chunks (list[dict]): ranked results, each containing:
                chunk_id (int)
                section_name (str)
                clause_number (str)
                chunk_text (str)
                keyword_match (bool): True if matched via full-text search
                semantic_score (float): cosine similarity score (0–1)
            error (str | None): error message if something went wrong, else None
    """
    try:
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            return {"chunks": [], "error": "OPENAI_API_KEY env var not set."}

        database_url = os.getenv("NEON_DATABASE_URL")
        if not database_url:
            return {"chunks": [], "error": "NEON_DATABASE_URL env var not set."}

        if not query or not query.strip():
            return {"chunks": [], "error": "query must not be empty."}

        if top_k < 1:
            return {"chunks": [], "error": "top_k must be at least 1."}

        # Step 1 — Generate query embedding
        client = OpenAI(api_key=openai_api_key)
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=query,
        )
        query_embedding: list[float] = response.data[0].embedding

        # Step 2 — Semantic search via pgvector cosine similarity
        semantic_query = """
            SELECT
                chunk_id,
                section_name,
                clause_number,
                chunk_text,
                1 - (embedding <=> %s::vector) AS semantic_score
            FROM ca_embeddings
            WHERE deal_id = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
        """

        # Step 3 — Full-text keyword search via ts_rank
        keyword_query = """
            SELECT
                chunk_id,
                section_name,
                clause_number,
                chunk_text,
                ts_rank(chunk_tsv, plainto_tsquery('english', %s)) AS rank
            FROM ca_embeddings
            WHERE deal_id = %s
              AND chunk_tsv @@ plainto_tsquery('english', %s)
            ORDER BY rank DESC
            LIMIT %s;
        """

        with psycopg2.connect(database_url) as conn:
            register_vector(conn)

            # Run semantic search
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(semantic_query, (query_embedding, deal_id, query_embedding, top_k))
                semantic_rows = [dict(row) for row in cur.fetchall()]

            # Run keyword search
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(keyword_query, (query, deal_id, query, top_k))
                keyword_rows = [dict(row) for row in cur.fetchall()]

        # Step 4 — Merge results with keyword-first ranking
        # Build a unified dict keyed by chunk_id, starting with semantic results
        result_map: dict[int, dict[str, Any]] = {}

        for row in semantic_rows:
            cid = row["chunk_id"]
            result_map[cid] = {
                "chunk_id": cid,
                "section_name": row["section_name"],
                "clause_number": row["clause_number"],
                "chunk_text": row["chunk_text"],
                "keyword_match": False,
                "semantic_score": float(row["semantic_score"]),
            }

        # Mark keyword matches — these take priority in final ranking
        keyword_chunk_ids: set[int] = set()
        for row in keyword_rows:
            cid = row["chunk_id"]
            keyword_chunk_ids.add(cid)
            if cid in result_map:
                # Already present from semantic search — just flip the flag
                result_map[cid]["keyword_match"] = True
            else:
                # Appeared only in keyword search — add with semantic_score=0.0
                result_map[cid] = {
                    "chunk_id": cid,
                    "section_name": row["section_name"],
                    "clause_number": row["clause_number"],
                    "chunk_text": row["chunk_text"],
                    "keyword_match": True,
                    "semantic_score": 0.0,
                }

        # Final sort: keyword matches first (desc semantic_score), then semantic-only (desc semantic_score)
        all_chunks = list(result_map.values())
        all_chunks.sort(key=lambda c: (not c["keyword_match"], -c["semantic_score"]))

        return {
            "chunks": all_chunks[:top_k],
            "error": None,
        }

    except Exception as e:
        return {"chunks": [], "error": str(e)}
