"""CA subgraph: extraction → validation only.

SQL storage, embedding, and HIL interrupts all live in the parent orchestrator
so LangSmith Studio Resume works correctly (same pattern as notice_branch).
"""

from typing import TypedDict, Optional, Annotated
from operator import add

from langgraph.graph import StateGraph, START, END

from agents.ca_extraction_agent import ca_extraction_agent
from agents.ca_validation_agent import ca_validation_agent


def _keep_last_error(a: Optional[str], b: Optional[str]) -> Optional[str]:
    return b if b is not None else a


# ---------------------------------------------------------------------------
# Input schema — only what the parent orchestrator provides
# ---------------------------------------------------------------------------

class CAInputState(TypedDict):
    raw_text: str
    r2_url: str


# ---------------------------------------------------------------------------
# Output schema — everything the orchestrator needs for routing + execution
# ---------------------------------------------------------------------------

class CAProcessingOutput(TypedDict):
    extracted_fields: dict
    confidence_flags: list
    validation_passed: bool
    validation_errors: list
    ca_hil_triggered: bool
    ca_hil_items: list
    error_message: Optional[str]


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

class CAState(TypedDict):
    raw_text: str
    r2_url: str
    extracted_fields: dict
    confidence_flags: list
    validation_passed: bool
    validation_errors: Annotated[list, add]
    ca_hil_triggered: bool
    ca_hil_items: list
    error_message: Annotated[Optional[str], _keep_last_error]


# ---------------------------------------------------------------------------
# Graph — pure computation, no interrupt(), exits normally every run
# ---------------------------------------------------------------------------

ca_builder = StateGraph(
    CAState,
    input_schema=CAInputState,
    output_schema=CAProcessingOutput,
)

ca_builder.add_node("ca_extraction_node", ca_extraction_agent)
ca_builder.add_node("ca_validation_node", ca_validation_agent)

ca_builder.add_edge(START, "ca_extraction_node")
ca_builder.add_edge("ca_extraction_node", "ca_validation_node")
ca_builder.add_edge("ca_validation_node", END)

ca_app = ca_builder.compile()
