"""Main orchestrator graph: classify PDF → route to CA or Notice subgraph.

All notice-branch HIL interrupt() calls live HERE (at the top-level graph)
so that LangSmith Studio's Resume correctly restores state and continues
execution instead of restarting from the beginning.
"""

import json
import re
import os
from typing import TypedDict, Optional, Annotated
from operator import add
from dotenv import load_dotenv

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent
from langgraph.types import interrupt

from tools.pdf_extract_tool import pdf_extract_tool
from tools.r2_upload_tool import r2_upload_tool
from graph.ca_branch import ca_app, CAState
from graph.notice_branch import notice_app
from agents.transaction_execution_agent import transaction_execution_agent

load_dotenv(override=True)


def _keep_last_error(a: Optional[str], b: Optional[str]) -> Optional[str]:
    return b if b is not None else a


# ---------------------------------------------------------------------------
# State schemas
# ---------------------------------------------------------------------------

class InputState(TypedDict):
    """Only field the user provides — Studio shows just this one input."""
    pdf_path: str


class GlobalState(TypedDict):
    # === Orchestrator ===
    pdf_path: str
    raw_text: str
    doc_type: str
    r2_url: str
    error_message: Annotated[Optional[str], _keep_last_error]

    # === Notice branch — populated by notice_branch subgraph ===
    notice_type: str
    extracted_fields: dict
    confidence_flags: list
    deal_record: dict
    borrower_record: dict
    risk_assessment_result: dict
    risk_hil_triggered: bool
    hard_stop: bool
    hard_stop_reason: Optional[str]
    validation_passed: bool
    validation_errors: Annotated[list, add]
    hil_triggered: bool
    hil_pending_items: Annotated[list, add]
    rag_results: list
    rag_validation_passed: bool

    # === Notice HIL decisions — populated by HIL nodes in this graph ===
    hil_decisions: Annotated[list, add]

    # === Transaction execution — populated by transaction_execution_node ===
    transaction_complete: bool
    transaction_summary: dict


# ---------------------------------------------------------------------------
# Orchestrator prompt + node
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


def orchestrator_node(state: GlobalState) -> dict:
    """Extract, upload, and classify the PDF. Sets doc_type, raw_text, r2_url."""
    llm = ChatAnthropic(model="claude-sonnet-4-5", temperature=0)
    tools = [pdf_extract_tool, r2_upload_tool]
    agent = create_react_agent(llm, tools)

    input_text = (
        f"Process the PDF at this path: {state['pdf_path']}\n\n"
        "1. Call pdf_extract_tool to get raw text.\n"
        "2. Call r2_upload_tool to upload the PDF (use doc_type='CA' as a placeholder).\n"
        "3. Classify the document as CA or Notice.\n"
        "4. Return JSON with: doc_type (str: CA/Notice/Unknown), raw_text (str), "
        "r2_url (str), error_message (str or null)."
    )

    result = agent.invoke({
        "messages": [SystemMessage(content=ORCHESTRATOR_PROMPT), HumanMessage(content=input_text)]
    })

    raw_content = result["messages"][-1].content
    if isinstance(raw_content, list):
        last_msg = " ".join(
            b.get("text", "") if isinstance(b, dict) else str(b)
            for b in raw_content
            if not isinstance(b, dict) or b.get("type") == "text"
        )
    else:
        last_msg = raw_content

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
# CA branch wrapper (no HIL — invoke subgraph directly)
# ---------------------------------------------------------------------------

def run_ca_branch(state: GlobalState) -> dict:
    """Invoke CA subgraph. CA has no HIL so a direct .invoke() is fine."""
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


# ---------------------------------------------------------------------------
# Notice branch HIL nodes — interrupt() lives HERE so Studio Resume works
# ---------------------------------------------------------------------------

def risk_hil_node(state: GlobalState) -> dict:
    """Interrupt: borrower risk escalated to High."""
    payload = {
        "trigger_reason": "Borrower risk escalated to High — human approval required",
        **state.get("risk_assessment_result", {}),
    }
    decision = interrupt(payload)
    decision_str = decision.get("decision", "Denied") if isinstance(decision, dict) else "Denied"
    return {
        "hil_decisions": [
            {
                "reason": "Risk Escalation to High",
                "decision": decision_str,
                "details": state.get("risk_assessment_result", {}),
            }
        ],
        "hil_triggered": True,
    }


def validation_hil_node(state: GlobalState) -> dict:
    """Interrupt: one or more validation / RAG checks require human review."""
    payload = {
        "trigger_reason": "One or more validation checks require human review",
        "items": state.get("hil_pending_items", []),
    }
    decision = interrupt(payload)
    decision_str = decision.get("decision", "Approved") if isinstance(decision, dict) else str(decision) if decision else "Approved"
    return {
        "hil_decisions": [
            {
                "reason": item.get("reason", ""),
                "decision": decision_str,
                "details": item.get("details", {}),
            }
            for item in state.get("hil_pending_items", [])
        ]
    }


def drawdown_hil_node(state: GlobalState) -> dict:
    """Interrupt: explicit human approval required before executing drawdown."""
    ef = state.get("extracted_fields", {})
    dr = state.get("deal_record", {})
    payload = {
        "trigger_reason": "Drawdown notice requires explicit human approval before execution",
        "drawdown_details": {
            "deal_name": ef.get("deal_name"),
            "drawdown_amount": ef.get("drawdown_amount"),
            "currency": ef.get("currency"),
            "payment_date": ef.get("payment_date"),
            "purpose_of_drawdown": ef.get("purpose_of_drawdown"),
        },
        "deal_state": {
            "committed_amount": dr.get("committed_amount"),
            "currently_funded": dr.get("funded"),
            "available_amount": (dr.get("committed_amount", 0) - dr.get("funded", 0)),
            "status": dr.get("status"),
        },
    }
    decision = interrupt(payload)
    decision_str = decision.get("decision", "Approved") if isinstance(decision, dict) else str(decision) if decision else "Approved"
    return {
        "hil_decisions": [
            {
                "reason": "Drawdown Approval",
                "decision": decision_str,
                "details": payload["drawdown_details"],
            }
        ],
        "hil_triggered": True,
    }


# ---------------------------------------------------------------------------
# Pass-through nodes
# ---------------------------------------------------------------------------

def _drawdown_check_passthrough(state: GlobalState) -> dict:
    return {}


def notice_end_node(state: GlobalState) -> dict:
    """Terminal notice node — logs final outcome."""
    if state.get("hard_stop"):
        print(f"[Notice] HARD STOP: {state.get('hard_stop_reason')}")
    elif state.get("error_message"):
        print(f"[Notice] ERROR: {state['error_message']}")
    elif state.get("transaction_complete"):
        print(f"[Notice] SUCCESS: {state.get('transaction_summary', {})}")
    else:
        denied = [d for d in state.get("hil_decisions", []) if d.get("decision") == "Denied"]
        print(f"[Notice] HALTED — denied HIL items: {denied}")
    return {}


def end_node(state: GlobalState) -> dict:
    """Final graph node."""
    if state.get("error_message") and not state.get("transaction_complete"):
        print(f"[Orchestrator] FAILED: {state['error_message']}")
    else:
        print(f"[Orchestrator] COMPLETED — doc_type={state.get('doc_type')}")
    return {}


# ---------------------------------------------------------------------------
# Routing functions
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


def route_after_notice_processing(state: GlobalState) -> str:
    """After notice subgraph completes: priority order for HIL routing."""
    if state.get("hard_stop", False):
        return "notice_end_node"
    if state.get("risk_hil_triggered", False):
        return "risk_hil_node"
    pending = state.get("hil_pending_items", [])
    rag_passed = state.get("rag_validation_passed", True)
    if pending or not rag_passed:
        return "validation_hil_node"
    return "drawdown_check_node"


def route_after_risk_hil(state: GlobalState) -> str:
    """After risk HIL — denied halts; approved checks if validation HIL also needed."""
    decisions = state.get("hil_decisions", [])
    risk_dec = next((d for d in decisions if d.get("reason") == "Risk Escalation to High"), None)
    if risk_dec and risk_dec.get("decision") == "Denied":
        return "notice_end_node"
    # Approved — check if validation HIL is also pending
    pending = state.get("hil_pending_items", [])
    rag_passed = state.get("rag_validation_passed", True)
    if pending or not rag_passed:
        return "validation_hil_node"
    return "drawdown_check_node"


def route_after_validation_hil(state: GlobalState) -> str:
    """After validation HIL — any Denied decision halts execution."""
    decisions = state.get("hil_decisions", [])
    validation_decisions = [
        d for d in decisions if d.get("reason") != "Risk Escalation to High"
    ]
    if any(d.get("decision") == "Denied" for d in validation_decisions):
        return "notice_end_node"
    return "drawdown_check_node"


def route_drawdown_check(state: GlobalState) -> str:
    """Drawdown always requires explicit approval; all other types go straight to execution."""
    if state.get("notice_type") == "Drawdown":
        return "drawdown_hil_node"
    return "transaction_execution_node"


def route_after_drawdown_hil(state: GlobalState) -> str:
    """After Drawdown HIL — approved executes, denied halts."""
    decisions = state.get("hil_decisions", [])
    dd_dec = next((d for d in decisions if d.get("reason") == "Drawdown Approval"), None)
    if dd_dec and dd_dec.get("decision") == "Denied":
        return "notice_end_node"
    return "transaction_execution_node"


# ---------------------------------------------------------------------------
# Main graph
# ---------------------------------------------------------------------------

main_builder = StateGraph(GlobalState, input=InputState)

# Shared nodes
main_builder.add_node("orchestrator_node", orchestrator_node)
main_builder.add_node("ca_branch", run_ca_branch)
main_builder.add_node("end_node", end_node)

# Notice processing subgraph (pure computation — no interrupt() inside)
main_builder.add_node("notice_branch", notice_app)

# Notice HIL nodes (interrupt() lives here, at the top-level graph)
main_builder.add_node("risk_hil_node", risk_hil_node)
main_builder.add_node("validation_hil_node", validation_hil_node)
main_builder.add_node("drawdown_hil_node", drawdown_hil_node)

# Notice pass-through and terminal nodes
main_builder.add_node("drawdown_check_node", _drawdown_check_passthrough)
main_builder.add_node("transaction_execution_node", transaction_execution_agent)
main_builder.add_node("notice_end_node", notice_end_node)

# ── Edges ──────────────────────────────────────────────────────────────────

main_builder.add_edge(START, "orchestrator_node")
main_builder.add_conditional_edges(
    "orchestrator_node",
    route_by_doc_type,
    ["ca_branch", "notice_branch", "end_node"],
)

# CA path
main_builder.add_edge("ca_branch", "end_node")

# Notice path: subgraph → HIL routing at parent level
main_builder.add_conditional_edges(
    "notice_branch",
    route_after_notice_processing,
    ["notice_end_node", "risk_hil_node", "validation_hil_node", "drawdown_check_node"],
)
main_builder.add_conditional_edges(
    "risk_hil_node",
    route_after_risk_hil,
    ["notice_end_node", "validation_hil_node", "drawdown_check_node"],
)
main_builder.add_conditional_edges(
    "validation_hil_node",
    route_after_validation_hil,
    ["notice_end_node", "drawdown_check_node"],
)
main_builder.add_conditional_edges(
    "drawdown_check_node",
    route_drawdown_check,
    ["drawdown_hil_node", "transaction_execution_node"],
)
main_builder.add_conditional_edges(
    "drawdown_hil_node",
    route_after_drawdown_hil,
    ["notice_end_node", "transaction_execution_node"],
)
main_builder.add_edge("transaction_execution_node", "notice_end_node")
main_builder.add_edge("notice_end_node", "end_node")
main_builder.add_edge("end_node", END)

# Compile without checkpointer — LangGraph API (Studio) injects its own persistence.
# For CLI use (main.py), call get_cli_app() which adds MemorySaver for HIL support.
app = main_builder.compile()


def get_cli_app():
    """Return a graph compiled with MemorySaver for local CLI / HIL use."""
    from langgraph.checkpoint.memory import MemorySaver
    return main_builder.compile(checkpointer=MemorySaver())
