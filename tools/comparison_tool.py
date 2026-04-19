from langchain_core.tools import tool


def _coerce(value: object) -> object:
    """Attempt to coerce a string to int or float for numeric comparison; return as-is otherwise."""
    if isinstance(value, str):
        try:
            as_int = int(value)
            return as_int
        except ValueError:
            pass
        try:
            as_float = float(value)
            return as_float
        except ValueError:
            pass
    return value


@tool
def comparison_tool(value_a: object, value_b: object, operator: str) -> dict:
    """Compare two values using a given operator; string equality is case-insensitive."""
    try:
        op = operator.strip()

        if op not in (">", "<", ">=", "<=", "=", "!="):
            return {
                "result": None,
                "error": (
                    f"Unknown operator '{operator}'. "
                    "Supported operators: '>', '<', '>=', '<=', '=', '!='."
                ),
            }

        # String equality/inequality: case-insensitive
        if op == "=" and isinstance(value_a, str) and isinstance(value_b, str):
            return {"result": value_a.strip().lower() == value_b.strip().lower(), "error": None}

        if op == "!=" and isinstance(value_a, str) and isinstance(value_b, str):
            return {"result": value_a.strip().lower() != value_b.strip().lower(), "error": None}

        # For ordering operators, attempt numeric coercion on strings so that
        # "1000" > "200" works numerically rather than lexicographically —
        # EXCEPT when both values look like YYYY-MM-DD dates, which compare
        # correctly as strings without coercion.
        import re
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        both_dates = (
            isinstance(value_a, str)
            and isinstance(value_b, str)
            and date_pattern.match(value_a.strip())
            and date_pattern.match(value_b.strip())
        )

        if not both_dates:
            value_a = _coerce(value_a)
            value_b = _coerce(value_b)

        if op == ">":
            result = value_a > value_b  # type: ignore[operator]
        elif op == "<":
            result = value_a < value_b  # type: ignore[operator]
        elif op == ">=":
            result = value_a >= value_b  # type: ignore[operator]
        elif op == "<=":
            result = value_a <= value_b  # type: ignore[operator]
        elif op == "=":
            result = value_a == value_b
        else:  # "!="
            result = value_a != value_b

        return {"result": bool(result), "error": None}

    except TypeError as e:
        return {
            "result": None,
            "error": f"Type mismatch — cannot compare values: {str(e)}",
        }
    except Exception as e:
        return {"result": None, "error": f"Comparison error: {str(e)}"}
