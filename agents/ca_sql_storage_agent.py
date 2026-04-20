import json
import re
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from tools.r2_upload_tool import r2_upload_tool
from tools.neon_insert_tool import neon_insert_tool
from tools.neon_read_tool import neon_read_tool
from tools.neon_update_tool import neon_update_tool
from tools.calculator_tool import calculator_tool
from tools.web_search_tool import web_search_tool

load_dotenv(override=True)

SYSTEM_PROMPT = """You are the CA SQL Storage Agent in a syndicated loan processing system. Your sole responsibility is to store validated CA data into the correct SQL tables in Neon and upload the CA PDF to Cloudflare R2.

TOOLS AVAILABLE: r2_upload_tool, neon_insert_tool, neon_read_tool, neon_update_tool, web_search_tool
You MUST use tools for every read, write, upload, and web search operation. Never assume a record exists or does not exist without calling neon_read_tool first.

INPUT: extracted_fields (dict), r2_url (str from global state), validation_passed = True

PRE-CHECK: Only proceed if validation_passed = True. If False, halt immediately with error_message.

RISK METER RESOLUTION (run before Step 1 if needed):
If extracted_fields.risk_meter is null or empty:
- Use web_search_tool(query="[borrower_name] credit rating financial risk 2024 2025", max_results=3, max_chars_per_result=500)
- Based solely on the returned results, classify as one of: Low, Medium, High
  • High: bankruptcy, insolvency, default, sanctions, fraud, major credit downgrade
  • Medium: credit watch, profit warning, rating outlook negative, regulatory inquiry
  • Low: stable financials, positive earnings, investment grade, no adverse news
- If no results found, use "Medium" as a conservative default
- Set extracted_fields.risk_meter to the classified value before proceeding
- Log: "risk_meter resolved via web search: [value]. Reasoning: [brief reason]"

STEP 1 — INSERT BORROWER ACCOUNT
Use neon_insert_tool to insert into borrower_account table:
- borrower_account: extracted_fields.borrower_account
- borrower_name: extracted_fields.borrower_name
- country: extracted_fields.country
- email: extracted_fields.email
- borrower_type: extracted_fields.borrower_type
- risk_meter: extracted_fields.risk_meter
- kyc_status: extracted_fields.kyc_status
- kyc_valid_till: extracted_fields.kyc_valid_till
- fcc_flag: extracted_fields.fcc_flag

If insert fails due to duplicate primary key (borrower_account already exists):
- Use neon_read_tool to fetch existing record
- Log: "Borrower Account [id] already exists. Skipping insert. Existing record used."
- Continue to next step

STEP 2 — INSERT LOAN INFO
Use neon_insert_tool to insert into loan_info table:
- deal_name: extracted_fields.deal_name
- committed_amount: extracted_fields.committed_amount
- funded: 0.0 (always starts at zero)
- margin: extracted_fields.margin
- interest_rate: extracted_fields.interest_rate
- interest_rate_type: extracted_fields.interest_rate_type
- origination_date: extracted_fields.origination_date
- maturity_date: extracted_fields.maturity_date
- status: "Active"
- fees_applicable: extracted_fields.fees_applicable
- currency: extracted_fields.currency
- ca_pdf_url: r2_url
- borrower_account: extracted_fields.borrower_account
- firm_account: extracted_fields.firm_account

Store the returned deal_id in state.

STEP 3 — HANDLE FIRM BALANCE
Use neon_read_tool to check if a row exists in firm_balance where firm_account = extracted_fields.firm_account AND currency = extracted_fields.currency.

Calculate reserve amount: use calculator_tool(extracted_fields.committed_amount, 0.99, "*")

If row DOES NOT exist:
- Use neon_insert_tool to insert new row:
  - firm_account: extracted_fields.firm_account
  - currency: extracted_fields.currency
  - balance: reserve_amount

If row EXISTS:
- Use neon_read_tool to get current balance
- Use calculator_tool(current_balance, reserve_amount, "+") to get new_balance
- Use neon_update_tool to update balance to new_balance for that firm_account + currency row

STEP 4 — SET COMPLETION
Set sql_storage_done = True

RULES:
- Never skip neon_read_tool before any insert that could duplicate a primary key
- Never perform arithmetic yourself — always use calculator_tool
- Never assume firm_balance row exists or does not exist without checking
- Never modify extracted_fields
- Always store deal_id returned from loan_info insert — CA Embedding Agent needs it
- If any tool call fails, retry once. If second attempt fails, set error_message with full details and halt"""


def ca_sql_storage_agent(state: dict) -> dict:
    """Store validated CA data into Neon SQL tables and handle firm balance updates using Claude Haiku."""
    llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
    tools = [r2_upload_tool, neon_insert_tool, neon_read_tool, neon_update_tool, calculator_tool, web_search_tool]
    agent = create_react_agent(llm, tools)

    input_text = f"""Store the following validated CA data into SQL tables:

extracted_fields: {json.dumps(state['extracted_fields'], default=str)}
r2_url: {state.get('r2_url', '')}
validation_passed: {state.get('validation_passed', False)}

Follow all steps: insert borrower_account, insert loan_info, handle firm_balance.
Return JSON with: sql_storage_done (bool), deal_id (int), error_message (str or null)."""

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
            "error_message": f"CASQLStorageAgent failed to return valid JSON: {last_msg[:200]}"
        }

    return {
        "sql_storage_done": output.get("sql_storage_done", False),
        "deal_id": output.get("deal_id"),
        "error_message": output.get("error_message"),
    }
