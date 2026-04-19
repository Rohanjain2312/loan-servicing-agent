"""Notice subgraph: extraction → risk → [validation ∥ RAG] → merge.

All interrupt() HIL calls and transaction execution live in the parent
orchestrator graph. This subgraph NEVER calls interrupt() so LangSmith
Studio's Resume works correctly at the top-level graph, not inside a
nested subgraph where checkpoint state can't be restored.
"""

from typing import TypedDict, Optional, Annotated
from operator import add

from langgraph.graph import StateGraph, START, END

from agents.notice_extraction_agent import notice_extraction_agent
from agents.risk_assessment_agent import risk_assessment_agent
from agents.notice_validation_agent import notice_validation_agent
from agents.rag_validation_agent import rag_validation_agent


def _keep_last_error(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Reducer for error_message: keep b if set, else keep a."""
    return b if b is not None else a


# ---------------------------------------------------------------------------
# Input schema — only raw_text and r2_url are required from the parent graph
# ---------------------------------------------------------------------------

class NoticeInputState(TypedDict):
    raw_text: str
    r2_url: str


# ---------------------------------------------------------------------------
# Output schema — every field the parent orchestrator needs for HIL routing
# and transaction execution. Must match the GlobalState field names exactly.
# ---------------------------------------------------------------------------

class NoticeProcessingOutput(TypedDict):
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
    validation_errors: list       # parent channel is Annotated[list, add]
    hil_triggered: bool
    hil_pending_items: list       # parent channel is Annotated[list, add]
    rag_results: list
    rag_validation_passed: bool
    error_message: Optional[str]


# ---------------------------------------------------------------------------
# Internal state — used only within this subgraph by agents
# ---------------------------------------------------------------------------

class NoticeState(TypedDict):
    # Input
    raw_text: str
    r2_url: str
    # Set by Notice Extraction Agent
    notice_type: str
    extracted_fields: dict
    confidence_flags: list
    # Set by Notice Validation Agent (fetches deal/borrower from DB)
    deal_record: dict
    borrower_record: dict
    # Set by Risk Assessment Agent
    risk_assessment_result: dict
    risk_hil_triggered: bool
    # Hard stop (set by Notice Validation Agent)
    hard_stop: bool
    hard_stop_reason: Optional[str]
    # Validation results
    validation_passed: bool
    validation_errors: Annotated[list, add]
    # HIL flags (set by validation/RAG agents — items to review)
    hil_triggered: bool
    hil_pending_items: Annotated[list, add]
    # RAG results
    rag_results: list
    rag_validation_passed: bool
    # Error — annotated so both parallel nodes can write it
    error_message: Annotated[Optional[str], _keep_last_error]


# ---------------------------------------------------------------------------
# Pass-through nodes
# ---------------------------------------------------------------------------

def validation_merge_node(state: NoticeState) -> dict:
    """Merge point after parallel validation — all routing happens in parent."""
    return {}


def _parallel_fan_out_node(state: NoticeState) -> dict:
    return {}


# ---------------------------------------------------------------------------
# Routing — fan-out only; all HIL routing is in the parent graph
# ---------------------------------------------------------------------------

def route_to_parallel_validation(state: NoticeState):
    """Fan out: both validation agents run concurrently."""
    return ["notice_validation_node", "rag_validation_node"]


# ---------------------------------------------------------------------------
# Graph — pure computation, NO interrupt() calls, exits normally every time
# ---------------------------------------------------------------------------

notice_builder = StateGraph(
    NoticeState,
    input_schema=NoticeInputState,
    output_schema=NoticeProcessingOutput,
)

notice_builder.add_node("notice_extraction_node", notice_extraction_agent)
notice_builder.add_node("risk_assessment_node", risk_assessment_agent)
notice_builder.add_node("notice_validation_node", notice_validation_agent)
notice_builder.add_node("rag_validation_node", rag_validation_agent)
notice_builder.add_node("validation_merge_node", validation_merge_node)
notice_builder.add_node("parallel_validation_fan_out", _parallel_fan_out_node)

notice_builder.add_edge(START, "notice_extraction_node")
notice_builder.add_edge("notice_extraction_node", "risk_assessment_node")
# Risk HIL routing is now in the parent — always fan out to parallel validation
notice_builder.add_edge("risk_assessment_node", "parallel_validation_fan_out")

notice_builder.add_conditional_edges(
    "parallel_validation_fan_out",
    route_to_parallel_validation,
    ["notice_validation_node", "rag_validation_node"],
)

notice_builder.add_edge("notice_validation_node", "validation_merge_node")
notice_builder.add_edge("rag_validation_node", "validation_merge_node")
notice_builder.add_edge("validation_merge_node", END)

notice_app = notice_builder.compile()
