"""CA subgraph: extraction → validation → SQL storage → deal_id check → embedding."""

from typing import TypedDict, Optional, Annotated
from operator import add

from langgraph.graph import StateGraph, START, END

from agents.ca_extraction_agent import ca_extraction_agent
from agents.ca_validation_agent import ca_validation_agent
from agents.ca_sql_storage_agent import ca_sql_storage_agent
from agents.ca_embedding_agent import ca_embedding_agent


def _keep_last_error(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Reducer for error_message: keep b if set, else keep a."""
    return b if b is not None else a


class CAState(TypedDict):
    # Passed in from global state
    raw_text: str
    r2_url: str
    # Set by CA Extraction Agent
    extracted_fields: dict
    confidence_flags: list
    # Set by CA Validation Agent
    validation_passed: bool
    validation_errors: Annotated[list, add]
    # Set by CA SQL Storage Agent (must complete before embedding)
    sql_storage_done: bool
    deal_id: Optional[int]
    # Set by CA Embedding Agent
    embedding_done: bool
    # Set by any agent on fatal halt
    error_message: Annotated[Optional[str], _keep_last_error]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def ca_end_node(state: CAState) -> dict:
    """Terminal node — logs outcome and exits CA subgraph."""
    if state.get("error_message"):
        print(f"[CA Branch] FAILED: {state['error_message']}")
    elif state.get("validation_passed") is False:
        errors = state.get("validation_errors", [])
        print(f"[CA Branch] VALIDATION FAILED: {errors}")
    else:
        print(
            f"[CA Branch] SUCCESS — deal_id={state.get('deal_id')} "
            f"sql_done={state.get('sql_storage_done')} "
            f"embed_done={state.get('embedding_done')}"
        )
    return {}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_after_ca_validation(state: CAState) -> str:
    """Proceed to SQL storage, or halt on validation failure."""
    if state.get("validation_passed", False):
        return "ca_sql_storage_node"
    return "ca_end_node"


def route_after_sql_storage(state: CAState) -> str:
    """Only run embedding if SQL storage succeeded and deal_id was set."""
    if state.get("error_message"):
        return "ca_end_node"
    deal_id = state.get("deal_id")
    if not deal_id or deal_id <= 0:
        return "ca_end_node"
    return "ca_embedding_node"


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

ca_builder = StateGraph(CAState)

ca_builder.add_node("ca_extraction_node", ca_extraction_agent)
ca_builder.add_node("ca_validation_node", ca_validation_agent)
ca_builder.add_node("ca_sql_storage_node", ca_sql_storage_agent)
ca_builder.add_node("ca_embedding_node", ca_embedding_agent)
ca_builder.add_node("ca_end_node", ca_end_node)

ca_builder.add_edge(START, "ca_extraction_node")
ca_builder.add_edge("ca_extraction_node", "ca_validation_node")
ca_builder.add_conditional_edges(
    "ca_validation_node",
    route_after_ca_validation,
    ["ca_sql_storage_node", "ca_end_node"],
)
# Embedding only runs after SQL storage confirms deal_id is valid
ca_builder.add_conditional_edges(
    "ca_sql_storage_node",
    route_after_sql_storage,
    ["ca_embedding_node", "ca_end_node"],
)
ca_builder.add_edge("ca_embedding_node", "ca_end_node")
ca_builder.add_edge("ca_end_node", END)

ca_app = ca_builder.compile()
