"""
embed_and_store_tool.py — Generate OpenAI text-embedding-3-small embeddings and store
them in the ca_embeddings Neon PostgreSQL table via pgvector.
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
EMBEDDING_DIMENSIONS = 1536


@tool
def embed_and_store_tool(
    deal_id: int,
    section_name: str,
    clause_number: str,
    chunk_text: str,
) -> dict[str, Any]:
    """
    Generate a vector embedding for a CA text chunk and store it in ca_embeddings.

    Steps:
      1. Call OpenAI Embeddings API with text-embedding-3-small.
      2. Insert the resulting 1536-dimensional vector into ca_embeddings via pgvector.

    Args:
        deal_id: Mandatory deal identifier used for retrieval filtering.
        section_name: CA section name e.g. "Conditions Precedent".
        clause_number: Clause identifier e.g. "5.1" or "5.1(a)".
        chunk_text: Full text of the chunk to embed and store.

    Returns:
        Dict with keys:
            chunk_id (int): auto-generated ID of the stored chunk
            embedding_dimensions (int): 1536 for text-embedding-3-small
            error (str | None): error message if something went wrong, else None
    """
    try:
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            return {"chunk_id": None, "embedding_dimensions": 0, "error": "OPENAI_API_KEY env var not set."}

        database_url = os.getenv("NEON_DATABASE_URL")
        if not database_url:
            return {"chunk_id": None, "embedding_dimensions": 0, "error": "NEON_DATABASE_URL env var not set."}

        if not chunk_text or not chunk_text.strip():
            return {"chunk_id": None, "embedding_dimensions": 0, "error": "chunk_text must not be empty."}

        # Step 1 — Generate embedding via OpenAI
        client = OpenAI(api_key=openai_api_key)
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=chunk_text,
        )
        embedding: list[float] = response.data[0].embedding

        if len(embedding) != EMBEDDING_DIMENSIONS:
            return {
                "chunk_id": None,
                "embedding_dimensions": len(embedding),
                "error": f"Unexpected embedding dimensions: {len(embedding)} (expected {EMBEDDING_DIMENSIONS}).",
            }

        # Step 2 — Insert into ca_embeddings with pgvector
        insert_query = """
            INSERT INTO ca_embeddings (deal_id, section_name, clause_number, chunk_text, embedding)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING chunk_id;
        """

        with psycopg2.connect(database_url) as conn:
            register_vector(conn)
            with conn.cursor() as cur:
                cur.execute(
                    insert_query,
                    (deal_id, section_name, clause_number, chunk_text, embedding),
                )
                chunk_id: int = cur.fetchone()[0]
            conn.commit()

        return {
            "chunk_id": chunk_id,
            "embedding_dimensions": EMBEDDING_DIMENSIONS,
            "error": None,
        }

    except Exception as e:
        return {"chunk_id": None, "embedding_dimensions": 0, "error": str(e)}
