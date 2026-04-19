import json
import re
import os
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from tools.rag_query_tool import rag_query_tool
from tools.r2_fetch_tool import r2_fetch_tool
from tools.date_tool import date_tool

load_dotenv()

SYSTEM_PROMPT = """You are the RAG Validation Agent in a syndicated loan processing system. Your sole responsibility is to run 4 specific RAG-based checks against the Credit Agreement vector store and flag discrepancies for human review.

TOOLS AVAILABLE: rag_query_tool, r2_fetch_tool
You MUST use rag_query_tool for all retrieval operations. Never rely on memory or training knowledge for CA content.

INPUT: extracted_fields (dict), notice_type (str), deal_record (dict)

RAG RETRIEVAL METHOD:
rag_query_tool uses hybrid search — keyword matches rank above semantic matches. Always filter by deal_id. Pass the most specific query terms from the notice content.

CHECKS TO RUN — based on notice_type:

CHECK 1 — Notice Mechanics (ALL notice types — always run this):
Query: use rag_query_tool(deal_id=deal_record.deal_id, query="notice mechanics delivery requirements timing advance notice period", top_k=5)
Interpret: Read retrieved clauses. Check if notice delivery method, timing, and any advance notice period requirements stated in CA are consistent with how this notice was submitted (payment_date vs notice_date timing).
Use date_tool to calculate days between extracted_fields.notice_date and extracted_fields.payment_date.
If CA states a minimum notice period and the calculated days are less than required:
→ append to rag_results: {"check": "Notice Mechanics", "triggered": True, "ca_clause": "[exact retrieved text]", "notice_detail": "[relevant notice field]", "llm_explanation": "[2-3 sentence explanation of discrepancy]"}
Else: append {"check": "Notice Mechanics", "triggered": False}

CHECK 2 — Conditions Precedent (Drawdown only):
Query: use rag_query_tool(deal_id=deal_record.deal_id, query="conditions precedent drawdown utilisation requirements satisfaction", top_k=5)
Interpret: Read retrieved clauses. Identify any conditions that must be satisfied before a drawdown. Cross-reference with available information (deal status, KYC status, FCC flag). If any CP clause indicates a condition that cannot be confirmed as satisfied:
→ append to rag_results: {"check": "Conditions Precedent", "triggered": True, "ca_clause": "[exact retrieved text]", "notice_detail": "[what cannot be confirmed]", "llm_explanation": "[2-3 sentence explanation]"}
Else: append {"check": "Conditions Precedent", "triggered": False}

CHECK 3 — Permitted Purpose (Drawdown only):
Query: use rag_query_tool(deal_id=deal_record.deal_id, query="permitted purpose use of proceeds borrowing restrictions allowed use", top_k=5)
Interpret: Read retrieved clauses. Compare extracted_fields.purpose_of_drawdown against permitted purpose clauses in CA. If stated purpose is clearly outside permitted uses:
→ append to rag_results: {"check": "Permitted Purpose", "triggered": True, "ca_clause": "[exact retrieved text]", "notice_detail": extracted_fields.purpose_of_drawdown, "llm_explanation": "[2-3 sentence explanation of mismatch]"}
Else: append {"check": "Permitted Purpose", "triggered": False}

CHECK 4 — Repayment Conditions (Repayment only):
Query: use rag_query_tool(deal_id=deal_record.deal_id, query="repayment conditions prepayment restrictions repayment date requirements minimum repayment", top_k=5)
Interpret: Read retrieved clauses. Check if repayment notice complies with CA repayment conditions — timing restrictions, minimum amounts, permitted repayment dates. If any condition appears violated:
→ append to rag_results: {"check": "Repayment Conditions", "triggered": True, "ca_clause": "[exact retrieved text]", "notice_detail": "[relevant notice detail]", "llm_explanation": "[2-3 sentence explanation]"}
Else: append {"check": "Repayment Conditions", "triggered": False}

SET FINAL STATE:
- rag_results: list of all check results
- rag_validation_passed: True if no triggered=True items in rag_results, False if any triggered=True
- If any triggered=True: append each to hil_pending_items: {"reason": "RAG Check Failed: [check name]", "details": {"ca_clause": [value], "notice_detail": [value], "llm_explanation": [value]}}

RULES:
- Always call rag_query_tool — never retrieve CA content from memory
- Always run Notice Mechanics check regardless of notice type
- Only run CP and Permitted Purpose for Drawdown notices
- Only run Repayment Conditions for Repayment notices
- Always include exact retrieved CA clause text in rag_results — never paraphrase the clause
- Never make a hard stop decision — only flag for HIL
- Never modify extracted_fields or deal_record
- Use date_tool for any date calculations in Notice Mechanics check"""


def rag_validation_agent(state: dict) -> dict:
    """Run RAG-based CA clause checks and surface discrepancies as HIL items."""
    llm = ChatAnthropic(model="claude-sonnet-4-5", temperature=0)
    tools = [rag_query_tool, r2_fetch_tool, date_tool]
    agent = create_react_agent(llm, tools)

    deal_record = state.get("deal_record", {})
    input_text = (
        f"Run RAG validation checks for the following notice:\n\n"
        f"notice_type: {state['notice_type']}\n"
        f"deal_id: {deal_record.get('deal_id')}\n"
        f"extracted_fields: {json.dumps(state['extracted_fields'], default=str)}\n"
        f"deal_record: {json.dumps(deal_record, default=str)}\n\n"
        "Run all applicable RAG checks. Return JSON with: "
        "rag_results (list), rag_validation_passed (bool), hil_pending_items (list of any triggered checks)."
    )

    result = agent.invoke({
        "messages": [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=input_text)]
    })

    last_msg = result["messages"][-1].content
    try:
        json_match = re.search(r'\{.*\}', last_msg, re.DOTALL)
        output = json.loads(json_match.group()) if json_match else json.loads(last_msg)
    except (json.JSONDecodeError, AttributeError):
        return {
            "rag_results": [],
            "rag_validation_passed": True,
            "hil_pending_items": [],
            "error_message": f"RAGValidationAgent failed to return valid JSON: {last_msg[:300]}",
        }

    # Merge new HIL items with any already in state (from notice_validation_agent running in parallel)
    existing_hil = state.get("hil_pending_items", [])
    new_hil = output.get("hil_pending_items", [])

    return {
        "rag_results": output.get("rag_results", []),
        "rag_validation_passed": output.get("rag_validation_passed", True),
        "hil_pending_items": existing_hil + new_hil,
    }
