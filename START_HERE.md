# START HERE — Claude Code Instructions

## Step 1 — Read These Files First
Before writing any code, read both files in full:
1. `CLAUDE.md` — project rules, structure, environment setup, critical constraints
2. `MasterPlan.md` — every design decision made for this project

Do not assume anything not documented in these two files.
Do not make any design decisions — they are all already made.

## Step 2 — Reference Docs for External Libraries
Read these before implementing the relevant component:
- LangSmith + LangGraph tracing: https://docs.langchain.com/langsmith/trace-with-langgraph
- LangGraph HIL + interrupt(): https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/
- LangGraph subgraphs: https://langchain-ai.github.io/langgraph/how-tos/subgraph/
- pgvector Python: https://github.com/pgvector/pgvector-python
- PyMuPDF: https://pymupdf.readthedocs.io/en/latest/
- Cloudflare R2 + boto3: https://developers.cloudflare.com/r2/api/s3/sdk/python/

## Step 3 — Build Order
Build in this exact order. Do not skip ahead.
1. `db/schema.sql` — MasterPlan.md Section 9 (SQL tables)
2. `tools/` — MasterPlan.md Section 16 (all 15 tools, sources, specs)
3. `agents/` — MasterPlan.md Section 15 (system prompts) + Section 4 (tool scoping)
4. `graph/` — MasterPlan.md Section 12 (nodes, edges, states)
5. `main.py` — CLI entry point accepting --pdf argument
6. `db/seed.sql` — 10-15 demo deals covering varied scenarios
7. `tests/sample_pdfs/` — sample CA and Notice PDFs for smoke testing

## Step 4 — MasterPlan Sync Rule
If any decision changes during development — workflow, agent logic, tool behaviour,
validation rule — update MasterPlan.md immediately before continuing.
Code and MasterPlan.md must always match.
