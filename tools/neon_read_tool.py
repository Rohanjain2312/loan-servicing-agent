"""
neon_read_tool.py — Parameterized SELECT from Neon PostgreSQL.
Allowed tables: borrower_account, loan_info, firm_balance, transaction_log, ca_embeddings
No DELETE statements anywhere in this file.
"""

from langchain_core.tools import tool
import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from typing import Any

load_dotenv()

ALLOWED_TABLES = {
    "borrower_account",
    "loan_info",
    "firm_balance",
    "transaction_log",
    "ca_embeddings",
}


@tool
def neon_read_tool(
    table: str,
    filters: dict[str, Any],
    columns: list[str] | None = None,
) -> dict[str, Any]:
    """
    Read rows from a Neon PostgreSQL table using parameterized queries.

    Args:
        table: One of borrower_account, loan_info, firm_balance, transaction_log, ca_embeddings.
        filters: Key-value pairs combined with AND logic in the WHERE clause.
        columns: List of column names to return. If None, all columns are returned.

    Returns:
        Dict with keys:
            rows (list[dict]): matching rows as plain dicts
            row_count (int): number of rows returned
            error (str | None): error message if something went wrong, else None
    """
    try:
        # Validate table name against allowlist to prevent SQL injection
        if table not in ALLOWED_TABLES:
            return {
                "rows": [],
                "row_count": 0,
                "error": f"Table '{table}' is not allowed. Must be one of: {sorted(ALLOWED_TABLES)}",
            }

        # Build SELECT clause
        if columns:
            # Validate column identifiers — only allow alphanumeric + underscore
            for col in columns:
                if not _is_safe_identifier(col):
                    return {
                        "rows": [],
                        "row_count": 0,
                        "error": f"Invalid column name '{col}'. Only alphanumeric characters and underscores are allowed.",
                    }
            select_clause = ", ".join(columns)
        else:
            select_clause = "*"

        # Build WHERE clause
        where_clause = ""
        params: list[Any] = []

        if filters:
            for key in filters:
                if not _is_safe_identifier(key):
                    return {
                        "rows": [],
                        "row_count": 0,
                        "error": f"Invalid filter key '{key}'. Only alphanumeric characters and underscores are allowed.",
                    }
            conditions = [f"{key} = %s" for key in filters]
            where_clause = "WHERE " + " AND ".join(conditions)
            params = list(filters.values())

        query = f"SELECT {select_clause} FROM {table} {where_clause};"

        database_url = os.getenv("NEON_DATABASE_URL")
        if not database_url:
            return {"rows": [], "row_count": 0, "error": "NEON_DATABASE_URL env var not set."}

        with psycopg2.connect(database_url) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params)
                rows = [dict(row) for row in cur.fetchall()]

        return {
            "rows": rows,
            "row_count": len(rows),
            "error": None,
        }

    except Exception as e:
        return {"rows": [], "row_count": 0, "error": str(e)}


def _is_safe_identifier(name: str) -> bool:
    """Return True if the identifier contains only alphanumeric chars and underscores."""
    return name.replace("_", "").isalnum()
