from langchain_core.tools import tool
from datetime import datetime, timezone, timedelta
from dateutil import parser as dateutil_parser


@tool
def date_tool(
    operation: str,
    date_a: str | None = None,
    date_b: str | None = None,
) -> dict:
    """Handle date operations: today's date, parsing, calendar day-difference, business day count, or UTC timestamp.

    Operations:
    - today: returns today's date as YYYY-MM-DD
    - parse: parses date_a into YYYY-MM-DD
    - diff_days: calendar days from date_a to date_b (date_b - date_a)
    - business_days: count Mon-Fri days strictly between date_a (exclusive) and date_b (inclusive)
    - timestamp: returns current UTC timestamp
    """
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

        elif op == "business_days":
            if not date_a or not date_b:
                return {
                    "result": None,
                    "error": "Both 'date_a' and 'date_b' are required for 'business_days'.",
                }
            try:
                dt_a = dateutil_parser.parse(date_a, fuzzy=False)
                dt_b = dateutil_parser.parse(date_b, fuzzy=False)
            except (ValueError, OverflowError) as e:
                return {
                    "result": None,
                    "error": f"Cannot parse one or both dates ('{date_a}', '{date_b}'): {str(e)}",
                }
            # Count Mon-Fri days strictly after date_a up to and including date_b.
            # This mirrors the finance convention: "X business days prior to utilisation"
            # means X weekdays must exist between the notice date and the payment date.
            count = 0
            current = dt_a + timedelta(days=1)
            while current.date() <= dt_b.date():
                if current.weekday() < 5:  # 0=Mon … 4=Fri
                    count += 1
                current += timedelta(days=1)
            return {"result": count, "error": None}

        else:
            return {
                "result": None,
                "error": (
                    f"Unknown operation '{operation}'. "
                    "Supported operations: 'today', 'parse', 'diff_days', 'business_days', 'timestamp'."
                ),
            }

    except Exception as e:
        return {"result": None, "error": f"Unexpected error in date_tool: {str(e)}"}
