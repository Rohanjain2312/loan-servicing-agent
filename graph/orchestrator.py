"""Main orchestrator graph: classify PDF → route to CA or Notice subgraph."""

import json
import re
import os
from typing import TypedDict, Optional
from dotenv import load_dotenv

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from tools.pdf_extract_tool import pdf_extract_tool
from tools.r2_upload_tool import r2_upload_tool
from graph.ca_branch import ca_app, CAState
from graph.notice_branch import notice_app, NoticeState

load_dotenv()

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

class GlobalState(TypedDict):
    pdf_path: str
    raw_text: str
    doc_type: str          # "CA" or "Notice"
    r2_url: str
    error_message: Optional[str]


# ---------------------------------------------------------------------------
# Orchestrator system prompt (verbatim from MasterPlan Section 15.1)
# ---------------------------------------------------------------------------

ORCHESTRATOR_PROMPT = """You are the Main Orchestrator of a syndicated loan processing system. Your sole responsibility is to classify an incoming PDF document as either a Credit Agreement (CA) or a Notice, and route it to the correct processing branch.

TOOLS AVAILABLE: pdf_extract_tool, r2_upload_tool
You MUST use tools for every action. Never process, read, or assume document content without using pdf_extract_tool first.

STEP 1 — EXTRACT
Use pdf_extract_tool on the provided PDF file path. This returns raw text. Do not attempt to read or interpret the PDF yourself.

STEP 2 — UPLOAD
Use r2_upload_tool to upload the PDF immediately after extraction. Store the returned URL in r2_url. Do not skip this step even if classification fails later.

STEP 3 — CLASSIFY
Read the raw text returned by pdf_extract_tool. Classify the document as CA or Notice using the following rules:

Classify as CA if ANY of these are present:
- Words or phrases: "Credit Agreement", "Facility Agreement", "Loan Agreement", "Term Sheet", "Commitment", "Conditions Precedent", "Representations and Warranties", "Covenants"
- Document contains sections defining borrower obligations, interest rates, maturity dates, and committed amounts
- Document is typically long (>2000 words) and structured as a legal contract

Classify as Notice if ANY of these are present:
- Words or phrases: "Drawdown Notice", "Utilisation Request", "Repayment Notice", "Interest Payment Notice", "Fee Payment Notice", "Notice of Borrowing"
- Document references an existing deal by name or ID and requests a specific financial action
- Document is typically short (<1000 words) and structured as a formal letter or request

If document cannot be clearly classified as CA or Notice:
- Set error_message to: "Document type could not be determined. Document does not contain sufficient markers for CA or Notice classification."
- Route to end node. Do not proceed.

STEP 4 — ROUTE
- If CA: pass raw_text, r2_url, doc_type="CA" to CA branch
- If Notice: pass raw_text, r2_url, doc_type="Notice" to Notice branch

RULES:
- Never skip tool calls
- Never classify without calling pdf_extract_tool first
- Never make assumptions about document content
- Never perform any validation, extraction of specific fields, or processing beyond classification
- Your only outputs are: doc_type, raw_text, r2_url, and optionally error_message"""


# ---------------------------------------------------------------------------
# Orchestrator node
# ---------------------------------------------------------------------------

def orchestrator_node(state: GlobalState) -> dict:
    """Extract, upload, and classify the PDF. Sets doc_type, raw_text, r2_url."""
    llm = ChatAnthropic(model="claude-sonnet-4-5", temperature=0)
    tools = [pdf_extract_tool, r2_upload_tool]
    agent = create_react_agent(llm, tools)

    input_text = (
        f"Process the PDF at this path: {state['pdf_path']}\n\n"
        "1. Call pdf_extract_tool to get raw text.\n"
        "2. Call r2_upload_tool to upload the PDF (use doc_type='Unknown' until classified).\n"
        "3. Classify the document as CA or Notice.\n"
        "4. Return JSON with: doc_type (str: CA/Notice/Unknown), raw_text (str), "
        "r2_url (str), error_message (str or null)."
    )

    result = agent.invoke({
        "messages": [SystemMessage(content=ORCHESTRATOR_PROMPT), HumanMessage(content=input_text)]
    })

    last_msg = result["messages"][-1].content
    try:
        json_match = re.search(r'\{.*\}', last_msg, re.DOTALL)
        output = json.loads(json_match.group()) if json_match else json.loads(last_msg)
    except (json.JSONDecodeError, AttributeError):
        return {
            "error_message": f"Orchestrator failed to return valid JSON: {last_msg[:300]}",
            "doc_type": "Unknown",
            "raw_text": "",
            "r2_url": "",
        }

    return {
        "doc_type": output.get("doc_type", "Unknown"),
        "raw_text": output.get("raw_text", ""),
        "r2_url": output.get("r2_url", ""),
        "error_message": output.get("error_message"),
    }


# ---------------------------------------------------------------------------
# Branch wrapper nodes (state translation: GlobalState ↔ subgraph state)
# ---------------------------------------------------------------------------

def run_ca_branch(state: GlobalState) -> dict:
    """Invoke CA subgraph with the shared fields from global state."""
    ca_input: CAState = {
        "raw_text": state["raw_text"],
        "r2_url": state["r2_url"],
        "extracted_fields": {},
        "confidence_flags": [],
        "validation_passed": False,
        "validation_errors": [],
        "sql_storage_done": False,
        "embedding_done": False,
        "deal_id": None,
        "error_message": None,
    }
    result = ca_app.invoke(ca_input)
    return {"error_message": result.get("error_message")}


def run_notice_branch(state: GlobalState) -> dict:
    """Invoke Notice subgraph with the shared fields from global state."""
    notice_input: NoticeState = {
        "raw_text": state["raw_text"],
        "r2_url": state["r2_url"],
        "notice_type": "",
        "extracted_fields": {},
        "confidence_flags": [],
        "deal_record": {},
        "borrower_record": {},
        "risk_assessment_result": {},
        "risk_hil_triggered": False,
        "hard_stop": False,
        "hard_stop_reason": None,
        "validation_passed": False,
        "validation_errors": [],
        "hil_triggered": False,
        "hil_pending_items": [],
        "hil_decisions": [],
        "rag_results": [],
        "rag_validation_passed": True,
        "transaction_complete": False,
        "transaction_summary": {},
        "error_message": None,
    }
    result = notice_app.invoke(notice_input)
    return {"error_message": result.get("error_message")}


# ---------------------------------------------------------------------------
# End node
# ---------------------------------------------------------------------------

def end_node(state: GlobalState) -> dict:
    """Log final outcome."""
    if state.get("error_message"):
        print(f"[Orchestrator] FAILED: {state['error_message']}")
    else:
        print(f"[Orchestrator] COMPLETED — doc_type={state.get('doc_type')}")
    return {}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_by_doc_type(state: GlobalState) -> str:
    if state.get("error_message"):
        return "end_node"
    doc_type = state.get("doc_type", "Unknown")
    if doc_type == "CA":
        return "ca_branch"
    if doc_type == "Notice":
        return "notice_branch"
    return "end_node"


# ---------------------------------------------------------------------------
# Main graph
# ---------------------------------------------------------------------------

main_builder = StateGraph(GlobalState)

main_builder.add_node("orchestrator_node", orchestrator_node)
main_builder.add_node("ca_branch", run_ca_branch)
main_builder.add_node("notice_branch", run_notice_branch)
main_builder.add_node("end_node", end_node)

main_builder.add_edge(START, "orchestrator_node")
main_builder.add_conditional_edges(
    "orchestrator_node",
    route_by_doc_type,
    ["ca_branch", "notice_branch", "end_node"],
)
main_builder.add_edge("ca_branch", "end_node")
main_builder.add_edge("notice_branch", "end_node")
main_builder.add_edge("end_node", END)

# MemorySaver checkpointer enables HIL interrupt/resume via LangSmith Studio
checkpointer = MemorySaver()
app = main_builder.compile(checkpointer=checkpointer)
