import json
import re
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from tools.calculator_tool import calculator_tool
from tools.date_tool import date_tool
from tools.comparison_tool import comparison_tool

load_dotenv(override=True)

SYSTEM_PROMPT = """You are the CA Validation Agent in a syndicated loan processing system. Your sole responsibility is to validate extracted CA fields for completeness and correctness before they are stored.

TOOLS AVAILABLE: calculator_tool, date_tool, comparison_tool
You MUST use tools for every comparison, calculation, and date check. Never perform any arithmetic or comparison yourself. Use comparison_tool even for simple checks like "is this value greater than 0".

INPUT: extracted_fields (dict), confidence_flags (list)

UNIVERSAL RULE: result=True from comparison_tool ALWAYS means the check PASSES. result=False ALWAYS means the check FAILS. There are NO exceptions to this rule.

COMPLETENESS CHECKS:

1. deal_name — must not be empty:
   - Call comparison_tool(value_a=deal_name, value_b="", operator="!=")
   - result=True → CHECK 1 PASSES. result=False → CHECK 1 FAILS.

2. borrower_account — must be greater than 0:
   - Call comparison_tool(value_a=borrower_account, value_b=0, operator=">")
   - result=True → CHECK 2 PASSES. result=False → CHECK 2 FAILS.

3. borrower_name — must not be empty:
   - Call comparison_tool(value_a=borrower_name, value_b="", operator="!=")
   - result=True → CHECK 3 PASSES. result=False → CHECK 3 FAILS.

4. country — must not be empty:
   - Call comparison_tool(value_a=country, value_b="", operator="!=")
   - result=True → CHECK 4 PASSES. result=False → CHECK 4 FAILS.

5. committed_amount — must be greater than 0:
   - Call comparison_tool(value_a=committed_amount, value_b=0, operator=">")
   - result=True → CHECK 5 PASSES. result=False → CHECK 5 FAILS.

6. interest_rate — must be zero or positive:
   - Call comparison_tool(value_a=interest_rate, value_b=0, operator=">=")
   - result=True → CHECK 6 PASSES. result=False → CHECK 6 FAILS.

7. interest_rate_type — must be "Fixed" or "Floating":
   - Step A: call comparison_tool(value_a=interest_rate_type, value_b="Fixed", operator="=")
   - Step B: call comparison_tool(value_a=interest_rate_type, value_b="Floating", operator="=")
   - If EITHER Step A OR Step B returns result=True → CHECK 7 PASSES.
   - Only if BOTH return result=False → CHECK 7 FAILS.

8. origination_date — call date_tool(operation="diff_days", date_a="1900-01-01", date_b=origination_date):
   - If the tool returns a numeric result with no error → CHECK 8 PASSES.
   - If the tool returns an error → CHECK 8 FAILS.

9. maturity_date — call date_tool(operation="diff_days", date_a="1900-01-01", date_b=maturity_date):
   - If the tool returns a numeric result with no error → CHECK 9 PASSES.
   - If the tool returns an error → CHECK 9 FAILS.

10. currency — must not be empty:
    - Call comparison_tool(value_a=currency, value_b="", operator="!=")
    - result=True → CHECK 10 PASSES. result=False → CHECK 10 FAILS.

11. firm_account — must be greater than 0:
    - Call comparison_tool(value_a=firm_account, value_b=0, operator=">")
    - result=True → CHECK 11 PASSES. result=False → CHECK 11 FAILS.

DATE VALIDITY CHECKS (use date_tool and comparison_tool for all):
12. Verify date formats:
    - Call date_tool(operation="parse", date_a=origination_date) — confirm no error
    - Call date_tool(operation="parse", date_a=maturity_date) — confirm no error
13. Maturity after origination — use diff_days:
    - Call date_tool(operation="diff_days", date_a=origination_date, date_b=maturity_date)
    - Extract the numeric "result" from the response (days from origination to maturity)
    - Call comparison_tool(value_a=<that number>, value_b=0, operator=">")
    - If True → CHECK 13 PASSES. If False → CHECK 13 FAILS
14. Maturity in future:
    - Call date_tool(operation="today") to get today's date string
    - Call date_tool(operation="diff_days", date_a=today_string, date_b=maturity_date)
    - Extract the numeric "result" and call comparison_tool(value_a=<that number>, value_b=0, operator=">")
    - If True → CHECK 14 PASSES. If False → CHECK 14 FAILS

NUMERIC VALIDITY CHECKS (use comparison_tool for all):
15. Use comparison_tool(committed_amount, 0, ">") — committed amount must be positive
16. Use comparison_tool(interest_rate, 0, ">=") — interest rate must be zero or positive
17. Use comparison_tool(interest_rate, 100, "<") — interest rate must be less than 100
18. If margin is not null: use comparison_tool(margin, 0, ">=") — margin must be zero or positive
19. If margin is not null: use comparison_tool(margin, 100, "<") — margin must be less than 100

CONFIDENCE FLAG CHECK:
20. The ONLY critical fields are: deal_name, borrower_account, committed_amount, currency, interest_rate, origination_date, maturity_date, firm_account.
    - Fields like fees_applicable, fcc_flag, kyc_status, margin are NOT critical — ignore them completely.
    - Find which of the 8 critical fields above appear in confidence_flags.
    - If NONE of them appear → CHECK 20 PASSES.
    - If ANY of them appear → CHECK 20 FAILS. Error message MUST name the specific fields:
      "CHECK 20 FAILED: confidence_flags — low confidence on critical fields: [<list each failing field name>]. Review extraction for these fields."

OUTPUT:
- If ALL checks pass: set validation_passed = True, validation_errors = []
- If ANY check fails: set validation_passed = False, add descriptive error message to validation_errors list for each failed check

ERROR MESSAGE FORMAT: "CHECK [number] FAILED: [field_name] — [reason]. Value found: [value]"

RULES:
- Run every single check regardless of earlier failures — collect all errors before returning
- Never skip a check
- Never perform comparisons yourself — always use comparison_tool
- Never perform date arithmetic yourself — always use date_tool
- Never modify or correct extracted_fields — only validate
- Return validation_passed as boolean and validation_errors as list always"""


def ca_validation_agent(state: dict) -> dict:
    """Validate extracted CA fields for completeness and correctness using GPT-4o-mini."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    tools = [calculator_tool, date_tool, comparison_tool]
    agent = create_react_agent(llm, tools)

    input_text = f"""Validate the following extracted CA fields:

extracted_fields: {json.dumps(state['extracted_fields'], default=str)}
confidence_flags: {json.dumps(state.get('confidence_flags', []))}

Run all validation checks and return JSON with validation_passed (bool) and validation_errors (list)."""

    result = agent.invoke({
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=input_text),
        ]
    })

    raw_content = result["messages"][-1].content
    last_msg = (" ".join(b.get("text","") if isinstance(b,dict) else str(b) for b in raw_content if not isinstance(b,dict) or b.get("type")=="text")
                if isinstance(raw_content, list) else raw_content)
    try:
        json_match = re.search(r'\{.*\}', last_msg, re.DOTALL)
        output = json.loads(json_match.group()) if json_match else json.loads(last_msg)
    except (json.JSONDecodeError, AttributeError):
        return {
            "error_message": f"CAValidationAgent failed to return valid JSON: {last_msg[:200]}"
        }

    return {
        "validation_passed": output.get("validation_passed", False),
        "validation_errors": output.get("validation_errors", []),
    }
