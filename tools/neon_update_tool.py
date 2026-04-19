"""
neon_update_tool.py — Parameterized UPDATE on Neon PostgreSQL.
Allowed tables: loan_info, firm_balance, transaction_log
borrower_account is explicitly protected — updates to it are rejected.
No DELETE statements anywhere in this file.
"""

from langchain_core.tools import tool
import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from typing import Any

load_dotenv(override=True)

ALLOWED_TABLES = {
    "loan_info",
    "firm_balance",
    "transaction_log",
}

PROTECTED_TABLES = {"borrower_account"}


@tool
def neon_update_tool(
    table: str,
    filters: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, Any]:
    """
    Update rows in a Neon PostgreSQL table using a parameterized query.

    Args:
        table: One of loan_info, firm_balance, transaction_log.
               borrower_account is explicitly protected and will return an error.
        filters: Key-value pairs for the WHERE clause identifying the exact row to update.
        updates: Column-value pairs to SET on the matched row.

    Returns:
        Dict with keys:
            updated_row (dict): full row after the update (via RETURNING *)
            rows_affected (int): number of rows updated (should always be 1)
            error (str | None): error message if something went wrong, else None
    """
    try:
        if table in PROTECTED_TABLES:
            return {
                "updated_row": {},
                "rows_affected": 0,
                "error": f"Updates to '{table}' are not permitted. borrower_account is read-only.",
            }

        if table not in ALLOWED_TABLES:
            return {
                "updated_row": {},
                "rows_affected": 0,
                "error": f"Table '{table}' is not allowed. Must be one of: {sorted(ALLOWED_TABLES)}",
            }

        if not filters:
            return {
                "updated_row": {},
                "rows_affected": 0,
                "error": "filters must not be empty — at least one WHERE condition is required.",
            }

        if not updates:
            return {
                "updated_row": {},
                "rows_affected": 0,
                "error": "updates must not be empty — at least one column-value pair is required.",
            }

        # Validate all identifiers
        for col in list(updates.keys()) + list(filters.keys()):
            if not _is_safe_identifier(col):
                return {
                    "updated_row": {},
                    "rows_affected": 0,
                    "error": f"Invalid identifier '{col}'. Only alphanumeric characters and underscores are allowed.",
                }

        # Build SET clause
        set_parts = [f"{col} = %s" for col in updates]
        set_clause = ", ".join(set_parts)

        # Build WHERE clause
        where_parts = [f"{col} = %s" for col in filters]
        where_clause = " AND ".join(where_parts)

        query = f"UPDATE {table} SET {set_clause} WHERE {where_clause} RETURNING *;"

        # Parameters: SET values first, then WHERE values
        params = list(updates.values()) + list(filters.values())

        database_url = os.getenv("NEON_DATABASE_URL")
        if not database_url:
            return {
                "updated_row": {},
                "rows_affected": 0,
                "error": "NEON_DATABASE_URL env var not set.",
            }

        with psycopg2.connect(database_url) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params)
                rows_affected = cur.rowcount
                result_row = cur.fetchone()
                updated_row = dict(result_row) if result_row else {}
            conn.commit()

        return {
            "updated_row": updated_row,
            "rows_affected": rows_affected,
            "error": None,
        }

    except Exception as e:
        return {"updated_row": {}, "rows_affected": 0, "error": str(e)}


def _is_safe_identifier(name: str) -> bool:
    """Return True if the identifier contains only alphanumeric chars and underscores."""
    return name.replace("_", "").isalnum()
