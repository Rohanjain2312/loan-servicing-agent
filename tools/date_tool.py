from langchain_core.tools import tool
from datetime import datetime, timezone
from dateutil import parser as dateutil_parser


@tool
def date_tool(
    operation: str,
    date_a: str | None = None,
    date_b: str | None = None,
) -> dict:
    """Handle date operations: today's date, parsing, day-difference, or UTC timestamp."""
    try:
        op = operation.strip().lower()

        if op == "today":
            today_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            return {"result": today_str, "error": None}

        elif op == "timestamp":
            ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            return {"result": ts, "error": None}

        elif op == "parse":
            if not date_a:
                return {"result": None, "error": "'date_a' is required for the 'parse' operation."}
            try:
                parsed = dateutil_parser.parse(date_a, fuzzy=False)
                return {"result": parsed.strftime("%Y-%m-%d"), "error": None}
            except (ValueError, OverflowError) as e:
                return {"result": None, "error": f"Cannot parse date '{date_a}': {str(e)}"}

        elif op == "diff_days":
            if not date_a or not date_b:
                return {
                    "result": None,
                    "error": "Both 'date_a' and 'date_b' are required for 'diff_days'.",
                }
            try:
                dt_a = dateutil_parser.parse(date_a, fuzzy=False)
                dt_b = dateutil_parser.parse(date_b, fuzzy=False)
            except (ValueError, OverflowError) as e:
                return {
                    "result": None,
                    "error": f"Cannot parse one or both dates ('{date_a}', '{date_b}'): {str(e)}",
                }
            diff = (dt_b - dt_a).days
            return {"result": int(diff), "error": None}

        else:
            return {
                "result": None,
                "error": (
                    f"Unknown operation '{operation}'. "
                    "Supported operations: 'today', 'parse', 'diff_days', 'timestamp'."
                ),
            }

    except Exception as e:
        return {"result": None, "error": f"Unexpected error in date_tool: {str(e)}"}
