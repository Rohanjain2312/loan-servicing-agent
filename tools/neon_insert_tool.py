"""
neon_insert_tool.py — Parameterized INSERT into Neon PostgreSQL.
Allowed tables: borrower_account, loan_info, firm_balance, transaction_log
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
}


@tool
def neon_insert_tool(
    table: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """
    Insert a row into a Neon PostgreSQL table using a parameterized query.

    Args:
        table: One of borrower_account, loan_info, firm_balance, transaction_log.
        data: Column-value pairs for the INSERT statement.

    Returns:
        Dict with keys:
            inserted_row (dict): full inserted row including auto-generated fields
            error (str | None): error message if something went wrong, else None
    """
    try:
        if table not in ALLOWED_TABLES:
            return {
                "inserted_row": {},
                "error": f"Table '{table}' is not allowed. Must be one of: {sorted(ALLOWED_TABLES)}",
            }

        if not data:
            return {"inserted_row": {}, "error": "data dict must not be empty."}

        # Validate column identifiers
        for col in data:
            if not _is_safe_identifier(col):
                return {
                    "inserted_row": {},
                    "error": f"Invalid column name '{col}'. Only alphanumeric characters and underscores are allowed.",
                }

        columns = list(data.keys())
        values = list(data.values())
        col_clause = ", ".join(columns)
        placeholder_clause = ", ".join(["%s"] * len(columns))

        query = f"INSERT INTO {table} ({col_clause}) VALUES ({placeholder_clause}) RETURNING *;"

        database_url = os.getenv("NEON_DATABASE_URL")
        if not database_url:
            return {"inserted_row": {}, "error": "NEON_DATABASE_URL env var not set."}

        with psycopg2.connect(database_url) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, values)
                inserted_row = dict(cur.fetchone())
            conn.commit()

        return {
            "inserted_row": inserted_row,
            "error": None,
        }

    except Exception as e:
        return {"inserted_row": {}, "error": str(e)}


def _is_safe_identifier(name: str) -> bool:
    """Return True if the identifier contains only alphanumeric chars and underscores."""
    return name.replace("_", "").isalnum()
