"""Notice subgraph: extraction → risk → [validation ∥ RAG] → merge → execution."""

from typing import TypedDict, Optional, Annotated
from operator import add


# ---------------------------------------------------------------------------
# Input / output schemas — used so the parent graph can add this as a proper
# subgraph node. LangGraph maps matching keys from GlobalState; internal
# NoticeState fields are initialised to their channel defaults.
# ---------------------------------------------------------------------------

class NoticeInputState(TypedDict):
    """Fields passed in from the parent orchestrator graph."""
    raw_text: str
    r2_url: str


class NoticeOutputState(TypedDict):
    """Fields written back to the parent orchestrator graph."""
    error_message: Optional[str]


def _keep_last_error(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Reducer for error_message: keep b if set, else keep a. Handles parallel node updates."""
    return b if b is not None else a

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from agents.notice_extraction_agent import notice_extraction_agent
from agents.risk_assessment_agent import risk_assessment_agent
from agents.notice_validation_agent import notice_validation_agent
from agents.rag_validation_agent import rag_validation_agent
from agents.transaction_execution_agent import transaction_execution_agent


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class NoticeState(TypedDict):
    # Passed in from global state
    raw_text: str
    r2_url: str

    # Set by Notice Extraction Agent
    notice_type: str
    extracted_fields: dict
    confidence_flags: list

    # Fetched by Notice Validation Agent
    deal_record: dict
    borrower_record: dict

    # Set by Risk Assessment Agent
    risk_assessment_result: dict
    risk_hil_triggered: bool

    # Hard stop (set by Notice Validation Agent — halts immediately)
    hard_stop: bool
    hard_stop_reason: Optional[str]

    # Validation results
    validation_passed: bool
    validation_errors: Annotated[list, add]

    # HIL state — accumulated across agents (both parallel nodes may append)
    hil_triggered: bool
    hil_pending_items: Annotated[list, add]
    hil_decisions: Annotated[list, add]

    # RAG results — set by RAG Validation Agent (parallel)
    rag_results: list
    rag_validation_passed: bool

    # Final outcome — set by Transaction Execution Agent
    transaction_complete: bool
    transaction_summary: dict

    # Error — annotated so parallel nodes can both write it
    error_message: Annotated[Optional[str], _keep_last_error]


# ---------------------------------------------------------------------------
# HIL nodes
# ---------------------------------------------------------------------------

def risk_hil_node(state: NoticeState) -> dict:
    """Interrupt for risk-escalated-to-High decisions."""
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


def validation_hil_node(state: NoticeState) -> dict:
    """Interrupt for all accumulated validation + RAG HIL items."""
    payload = {
        "trigger_reason": "One or more validation checks require human review",
        "items": state.get("hil_pending_items", []),
    }
    decision = interrupt(payload)
    decision_str = decision.get("decision", "Denied") if isinstance(decision, dict) else "Denied"
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


def drawdown_hil_node(state: NoticeState) -> dict:
    """Interrupt required for ALL Drawdown notices before execution."""
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
    decision_str = decision.get("decision", "Denied") if isinstance(decision, dict) else "Denied"
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
# Pass-through / end nodes
# ---------------------------------------------------------------------------

def validation_merge_node(state: NoticeState) -> dict:
    """Pure logic pass-through — routing is handled in conditional edges."""
    return {}


def notice_end_node(state: NoticeState) -> dict:
    """Terminal node — logs outcome."""
    if state.get("hard_stop"):
        print(f"[Notice Branch] HARD STOP: {state.get('hard_stop_reason')}")
    elif state.get("error_message"):
        print(f"[Notice Branch] ERROR: {state['error_message']}")
    elif state.get("transaction_complete"):
        summary = state.get("transaction_summary", {})
        print(f"[Notice Branch] SUCCESS: {summary}")
    else:
        # Denied by human or halted
        decisions = state.get("hil_decisions", [])
        denied = [d for d in decisions if d.get("decision") == "Denied"]
        print(f"[Notice Branch] HALTED — denied HIL items: {denied}")
    return {}


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def route_after_risk_assessment(state: NoticeState) -> str:
    """Route to risk HIL or proceed to parallel validation."""
    if state.get("risk_hil_triggered", False):
        return "risk_hil_node"
    return "parallel_validation_fan_out"


def route_after_risk_hil(state: NoticeState) -> str:
    """After risk HIL — denied halts, approved continues."""
    decisions = state.get("hil_decisions", [])
    risk_decision = next(
        (d for d in decisions if d.get("reason") == "Risk Escalation to High"), None
    )
    if risk_decision and risk_decision.get("decision") == "Denied":
        return "notice_end_node"
    return "parallel_validation_fan_out"


def route_to_parallel_validation(state: NoticeState):
    """Fan out to both validation agents in parallel."""
    return ["notice_validation_node", "rag_validation_node"]


def route_after_merge(state: NoticeState) -> str:
    """Priority: hard_stop > HIL > drawdown check > execution."""
    if state.get("hard_stop", False):
        return "notice_end_node"
    pending = state.get("hil_pending_items", [])
    rag_passed = state.get("rag_validation_passed", True)
    if pending or not rag_passed:
        return "validation_hil_node"
    return "drawdown_check_node"


def route_after_validation_hil(state: NoticeState) -> str:
    """After validation HIL — check if any item was denied."""
    decisions = state.get("hil_decisions", [])
    # Exclude the risk escalation decision from check
    validation_decisions = [
        d for d in decisions if d.get("reason") != "Risk Escalation to High"
    ]
    if any(d.get("decision") == "Denied" for d in validation_decisions):
        return "notice_end_node"
    return "drawdown_check_node"


def route_drawdown_check(state: NoticeState) -> str:
    """Drawdown always requires HIL before execution."""
    if state.get("notice_type") == "Drawdown":
        return "drawdown_hil_node"
    return "transaction_execution_node"


def route_after_drawdown_hil(state: NoticeState) -> str:
    """After Drawdown HIL — denied halts, approved executes."""
    decisions = state.get("hil_decisions", [])
    drawdown_decision = next(
        (d for d in decisions if d.get("reason") == "Drawdown Approval"), None
    )
    if drawdown_decision and drawdown_decision.get("decision") == "Denied":
        return "notice_end_node"
    return "transaction_execution_node"


# Thin routing node for the parallel fan-out (can't conditionally return list from
# a node that was itself reached via conditional edges — needs its own node)
def _parallel_fan_out_node(state: NoticeState) -> dict:
    return {}


def _drawdown_check_passthrough(state: NoticeState) -> dict:
    return {}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

notice_builder = StateGraph(NoticeState, input_schema=NoticeInputState, output_schema=NoticeOutputState)

# Agent nodes
notice_builder.add_node("notice_extraction_node", notice_extraction_agent)
notice_builder.add_node("risk_assessment_node", risk_assessment_agent)
notice_builder.add_node("notice_validation_node", notice_validation_agent)
notice_builder.add_node("rag_validation_node", rag_validation_agent)
notice_builder.add_node("transaction_execution_node", transaction_execution_agent)

# HIL nodes
notice_builder.add_node("risk_hil_node", risk_hil_node)
notice_builder.add_node("validation_hil_node", validation_hil_node)
notice_builder.add_node("drawdown_hil_node", drawdown_hil_node)

# Logic / routing nodes
notice_builder.add_node("validation_merge_node", validation_merge_node)
notice_builder.add_node("parallel_validation_fan_out", _parallel_fan_out_node)
notice_builder.add_node("drawdown_check_node", _drawdown_check_passthrough)
notice_builder.add_node("notice_end_node", notice_end_node)

# Edges
notice_builder.add_edge(START, "notice_extraction_node")
notice_builder.add_edge("notice_extraction_node", "risk_assessment_node")

notice_builder.add_conditional_edges(
    "risk_assessment_node",
    route_after_risk_assessment,
    ["risk_hil_node", "parallel_validation_fan_out"],
)
notice_builder.add_conditional_edges(
    "risk_hil_node",
    route_after_risk_hil,
    ["notice_end_node", "parallel_validation_fan_out"],
)

# Fan-out: both validation nodes run in parallel
notice_builder.add_conditional_edges(
    "parallel_validation_fan_out",
    route_to_parallel_validation,
    ["notice_validation_node", "rag_validation_node"],
)

# Both parallel nodes converge on merge (state updates merged automatically)
notice_builder.add_edge("notice_validation_node", "validation_merge_node")
notice_builder.add_edge("rag_validation_node", "validation_merge_node")

notice_builder.add_conditional_edges(
    "validation_merge_node",
    route_after_merge,
    ["notice_end_node", "validation_hil_node", "drawdown_check_node"],
)
notice_builder.add_conditional_edges(
    "validation_hil_node",
    route_after_validation_hil,
    ["notice_end_node", "drawdown_check_node"],
)
notice_builder.add_conditional_edges(
    "drawdown_check_node",
    route_drawdown_check,
    ["drawdown_hil_node", "transaction_execution_node"],
)
notice_builder.add_conditional_edges(
    "drawdown_hil_node",
    route_after_drawdown_hil,
    ["notice_end_node", "transaction_execution_node"],
)
notice_builder.add_edge("transaction_execution_node", "notice_end_node")
notice_builder.add_edge("notice_end_node", END)

notice_app = notice_builder.compile()
