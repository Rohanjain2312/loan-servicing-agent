import json
import re
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from tools.embed_and_store_tool import embed_and_store_tool

load_dotenv(override=True)

SYSTEM_PROMPT = """You are the CA Embedding Agent in a syndicated loan processing system. Your sole responsibility is to chunk the full Credit Agreement text structurally, generate embeddings for each chunk, and store them in pgvector with correct metadata.

TOOLS AVAILABLE: embed_and_store_tool
You MUST use embed_and_store_tool for all embedding and storage operations. Never generate embeddings yourself.

INPUT: raw_text (str), deal_id (int from CA SQL Storage Agent)

CHUNKING INSTRUCTIONS:
Split raw_text into chunks using the following structural rules in order:
1. Split on major section headers — these are lines that begin with a number followed by a period or are in ALL CAPS e.g. "1. DEFINITIONS", "SCHEDULE 1", "CONDITIONS PRECEDENT"
2. Within each section, split further on sub-clause markers e.g. "(a)", "(b)", "(i)", "(ii)", "1.1", "1.2"
3. Each chunk must be one complete clause or sub-clause — never split mid-sentence
4. Minimum chunk size: 50 words. If a clause is shorter than 50 words, merge it with the next clause
5. Maximum chunk size: 400 words. If a clause exceeds 400 words, split at the nearest sentence boundary

For each chunk, identify:
- section_name: the heading of the parent section e.g. "Conditions Precedent", "Repayment", "Interest"
- clause_number: the clause identifier e.g. "5.1", "5.1(a)", "Schedule 1"
- chunk_text: the full text of the chunk

STORAGE:
For each chunk, call embed_and_store_tool with:
- deal_id: deal_id from input
- section_name: identified section name
- clause_number: identified clause number
- chunk_text: full chunk text

embed_and_store_tool handles embedding generation and pgvector storage internally.

COMPLETION:
After all chunks are stored, set embedding_done = True. Log total number of chunks stored.

RULES:
- Process every part of the raw_text — do not skip any section including schedules and annexures
- Never generate or store embeddings without using embed_and_store_tool
- Never store chunks without deal_id — this is mandatory for retrieval filtering
- Never truncate chunk_text before passing to embed_and_store_tool
- If embed_and_store_tool fails for a chunk, retry once. If second attempt fails, log the failed clause_number and continue with remaining chunks — do not halt entire process
- Set embedding_done = True only after all chunks attempted (including retries)"""


def ca_embedding_agent(state: dict) -> dict:
    """Chunk Credit Agreement text structurally and store embeddings in pgvector using GPT-4o-mini."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    tools = [embed_and_store_tool]
    agent = create_react_agent(llm, tools)

    input_text = f"""Chunk and embed the following Credit Agreement for deal_id={state['deal_id']}:

raw_text: {state['raw_text']}

Process all sections. Call embed_and_store_tool for each chunk.
Return JSON: embedding_done (bool), chunks_stored (int), error_message (str or null)."""

    result = agent.invoke({
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=input_text),
        ]
    })

    last_msg = result["messages"][-1].content
    try:
        json_match = re.search(r'\{.*\}', last_msg, re.DOTALL)
        output = json.loads(json_match.group()) if json_match else json.loads(last_msg)
    except (json.JSONDecodeError, AttributeError):
        return {
            "error_message": f"CAEmbeddingAgent failed to return valid JSON: {last_msg[:200]}"
        }

    return {
        "embedding_done": output.get("embedding_done", False),
        "error_message": output.get("error_message"),
    }
