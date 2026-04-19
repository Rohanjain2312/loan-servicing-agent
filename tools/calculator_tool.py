from langchain_core.tools import tool


@tool
def calculator_tool(value_a: float, value_b: float, operation: str) -> dict:
    """Perform a safe arithmetic operation between two values; all agents must use this, never compute inline."""
    try:
        op = operation.strip()

        if op == "+":
            result = value_a + value_b
        elif op == "-":
            result = value_a - value_b
        elif op == "*":
            result = value_a * value_b
        elif op == "/":
            if value_b == 0:
                return {"result": None, "error": "Division by zero is not allowed."}
            result = value_a / value_b
        elif op == "abs":
            result = abs(value_a)
        else:
            return {
                "result": None,
                "error": (
                    f"Unknown operation '{operation}'. "
                    "Supported operations: '+', '-', '*', '/', 'abs'."
                ),
            }

        return {"result": float(result), "error": None}

    except Exception as e:
        return {"result": None, "error": f"Calculation error: {str(e)}"}
