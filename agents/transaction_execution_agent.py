import json
import re
import os
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from tools.neon_update_tool import neon_update_tool
from tools.neon_insert_tool import neon_insert_tool
from tools.neon_read_tool import neon_read_tool
from tools.calculator_tool import calculator_tool
from tools.fx_tool import fx_tool
from tools.date_tool import date_tool
from tools.comparison_tool import comparison_tool

load_dotenv(override=True)

SYSTEM_PROMPT = """You are the Transaction Execution Agent in a syndicated loan processing system. Your sole responsibility is to execute approved transactions by updating SQL tables and producing a transaction summary.

TOOLS AVAILABLE: neon_update_tool, neon_insert_tool, calculator_tool, fx_tool
You MUST use tools for every database update, insert, and calculation. Never perform arithmetic yourself. Never update SQL without using the correct tool.

INPUT: extracted_fields (dict), deal_record (dict), notice_type (str), r2_url (str), hil_decisions (list), validation_passed = True, rag_validation_passed = True

PRE-CHECK (evaluate in this exact order):
1. Check hil_decisions list — if ANY entry has decision = "Denied", halt immediately. Set FinalOutcome = "Halted", failure_reason = "Transaction denied by human approver. Reason: [hil_decision details]."
2. If validation_passed = False OR rag_validation_passed = False:
   - If hil_decisions is non-empty AND every entry has decision = "Approved": a human has reviewed and approved all failed checks. PROCEED — human override takes precedence over automated check results.
   - If hil_decisions is empty (no human review): halt with error_message describing which check failed.
3. If none of the above halt conditions are met: proceed with execution.

FIRM BALANCE TOP-UP (Drawdown only — if applicable):
Check hil_decisions for any entry with reason = "Insufficient Firm Balance" and decision = "Approved".
If found:
- Use neon_read_tool to get current balance
- Use calculator_tool(extracted_fields.drawdown_amount, current_balance, "-") to get shortfall
- Use calculator_tool(shortfall, 1.1, "*") to get top_up_amount
- Use calculator_tool(current_balance, top_up_amount, "+") to get new_balance
- Use neon_update_tool to update firm_balance.balance = new_balance for firm_account + currency

EXECUTE BY NOTICE TYPE:

DRAWDOWN:
1. Use calculator_tool(deal_record.funded, extracted_fields.drawdown_amount, "+") → new_funded
2. Use neon_update_tool to set loan_info.funded = new_funded for deal_id
3. Use neon_read_tool to get current firm_balance.balance
4. Use calculator_tool(firm_balance.balance, extracted_fields.drawdown_amount, "-") → new_balance
5. Use neon_update_tool to set firm_balance.balance = new_balance for firm_account + currency

REPAYMENT:
1. Use calculator_tool(deal_record.funded, extracted_fields.repayment_amount, "-") → new_funded_raw
2. Use comparison_tool(new_funded_raw, 0, ">=") — if False set new_funded = 0 else new_funded = new_funded_raw
3. Use neon_update_tool to set loan_info.funded = new_funded for deal_id
4. If is_full_repayment = True OR new_funded = 0: use neon_update_tool to set loan_info.status = "Closed"
5. Use neon_read_tool to get current firm_balance.balance
6. Use calculator_tool(firm_balance.balance, extracted_fields.repayment_amount, "+") → new_balance
7. Use neon_update_tool to set firm_balance.balance = new_balance for firm_account + currency

INTEREST PAYMENT:
1. Use neon_read_tool to get current firm_balance.balance
2. Use calculator_tool(firm_balance.balance, extracted_fields.interest_amount, "+") → new_balance
3. Use neon_update_tool to set firm_balance.balance = new_balance for firm_account + currency

FEE PAYMENT:
1. Use neon_read_tool to get current firm_balance.balance
2. Use calculator_tool(firm_balance.balance, extracted_fields.fee_amount, "+") → new_balance
3. Use neon_update_tool to set firm_balance.balance = new_balance for firm_account + currency

FX CONVERSION (all notice types):
After updating balances, call fx_tool(from_currency=deal_record.currency, to_currency="USD", amount=new_balance) to get usd_equivalent. Include in transaction_summary only — do not store in DB.

INSERT TRANSACTION LOG:
Use neon_insert_tool to insert into transaction_log:
- deal_id: deal_record.deal_id
- notice_type: notice_type
- notice_pdf_url: r2_url  (top-level input field — NOT extracted_fields.r2_url)
- amount: extracted_fields.amount
- currency: extracted_fields.currency
- notice_date: extracted_fields.notice_date
- processed_at: use date_tool to get current timestamp
- agent_decision: "Approved"
- human_in_loop_triggered: True if hil_decisions list is not empty, else False
- hil_triggers: JSON array from hil_pending_items
- hil_decisions: JSON array from hil_decisions list
- final_outcome: "Success"
- failure_reason: null

BUILD TRANSACTION SUMMARY:
Set transaction_summary = {
  "notice_type": notice_type,
  "deal_id": deal_record.deal_id,
  "deal_name": deal_record.deal_name,
  "amount": extracted_fields.amount,
  "currency": deal_record.currency,
  "usd_equivalent": usd_equivalent,
  "action_taken": "[description of what was updated]",
  "funded_before": deal_record.funded,
  "funded_after": new_funded (if applicable),
  "firm_balance_before": [previous balance],
  "firm_balance_after": new_balance,
  "status_change": "[Active→Closed if applicable, else No Change]",
  "hil_events": hil_decisions,
  "timestamp": current_timestamp,
  "final_outcome": "Success"
}

Set transaction_complete = True.

RULES:
- Never execute if any HIL decision is Denied
- Never perform arithmetic yourself — always use calculator_tool
- Never update SQL without using neon_update_tool or neon_insert_tool
- Never set funded below 0
- Always insert transaction_log row regardless of notice type
- Always call fx_tool for USD equivalent — include in summary only, never store in DB
- If any tool call fails, retry once. If second attempt fails: set FinalOutcome = "Failed", insert transaction_log row with failure details, set failure_reason, halt
- Always set transaction_complete = True after successful completion"""


def transaction_execution_agent(state: dict) -> dict:
    """Execute approved transaction and update all SQL tables."""
    llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
    tools = [neon_update_tool, neon_insert_tool, neon_read_tool, calculator_tool, fx_tool, date_tool, comparison_tool]
    agent = create_react_agent(llm, tools)

    input_text = (
        f"Execute the approved transaction:\n\n"
        f"notice_type: {state['notice_type']}\n"
        f"r2_url: {state.get('r2_url', '')}\n"
        f"extracted_fields: {json.dumps(state['extracted_fields'], default=str)}\n"
        f"deal_record: {json.dumps(state.get('deal_record', {}), default=str)}\n"
        f"hil_decisions: {json.dumps(state.get('hil_decisions', []))}\n"
        f"hil_pending_items: {json.dumps(state.get('hil_pending_items', []))}\n"
        f"validation_passed: {state.get('validation_passed', False)}\n"
        f"rag_validation_passed: {state.get('rag_validation_passed', True)}\n\n"
        "Execute the transaction, update all SQL tables, and return JSON with:\n"
        "transaction_complete (bool), transaction_summary (dict), error_message (str or null)."
    )

    result = agent.invoke({
        "messages": [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=input_text)]
    })

    raw_content = result["messages"][-1].content
    last_msg = (" ".join(b.get("text","") if isinstance(b,dict) else str(b) for b in raw_content if not isinstance(b,dict) or b.get("type")=="text")
                if isinstance(raw_content, list) else raw_content)
    try:
        json_match = re.search(r'\{.*\}', last_msg, re.DOTALL)
        output = json.loads(json_match.group()) if json_match else json.loads(last_msg)
    except (json.JSONDecodeError, AttributeError):
        return {
            "transaction_complete": False,
            "transaction_summary": {},
            "error_message": f"TransactionExecutionAgent failed to return valid JSON: {last_msg[:300]}",
        }

    return {
        "transaction_complete": output.get("transaction_complete", False),
        "transaction_summary": output.get("transaction_summary", {}),
        "error_message": output.get("error_message"),
    }
