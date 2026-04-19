# Loan Servicing Agent — Claude Code Context

## Project
Multi-agent AI system for processing syndicated loan documents (Credit Agreements and Notices).
GitHub: https://github.com/Rohanjain2312/loan-servicing-agent.git
Primary demo interface: LangSmith Studio for tracing + HIL approvals.

## Master Reference
**Read `MasterPlan.md` before starting any task.**
It contains all design decisions, agent architecture, state schemas, node/edge graphs,
tool definitions, system prompts, and validation logic.
Do not assume anything not documented there.

## MasterPlan Sync Rule
If any workflow change, agent addition, tool change, or logic update is made during
development, `MasterPlan.md` must be updated to reflect it before moving to the next task.
The code and MasterPlan.md must always be in sync. At project end, MasterPlan.md is the
source of truth for what was built.

## Tech Stack
- Python 3.11+
- LangGraph — multi-agent graph with subgraphs and parallel nodes
- LangSmith — tracing (set LANGSMITH_TRACING=true + LANGSMITH_API_KEY + LANGSMITH_PROJECT)
- Claude Sonnet (`claude-sonnet-4-5`) — orchestrator, RAG agent, risk agent
- GPT-4o-mini — all other sub-agents
- Neon PostgreSQL + pgvector — relational tables + vector embeddings
- Cloudflare R2 (boto3 S3-compatible) — PDF storage
- PyMuPDF (fitz) — PDF text extraction
- rapidfuzz — fuzzy deal name matching
- python-dateutil — date parsing
- Tavily — web search (Risk Assessment Agent only)
- ExchangeRate-API — FX conversion

## LangSmith Setup
```
LANGSMITH_API_KEY=<your-key>
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=loan-servicing-agent
```
- LangGraph nodes trace automatically when env vars are set
- Wrap all direct Anthropic SDK and OpenAI SDK calls with `@traceable` decorator
- HIL interrupts handled via LangGraph `interrupt()` — visible in LangSmith Studio
- Docs: https://docs.smith.langchain.com/observability/how_to_guides/trace_with_langchain
- LangGraph tracing: https://docs.langchain.com/langsmith/trace-with-langgraph

## Project Structure
```
loan-servicing-agent/
├── CLAUDE.md
├── MasterPlan.md
├── .env                          # all API keys — never commit
├── .env.example                  # key names only, no values
├── requirements.txt
├── main.py                       # entry point: python main.py --pdf path/to/doc.pdf
├── graph/
│   ├── orchestrator.py           # main graph + global state
│   ├── ca_branch.py              # CA subgraph
│   └── notice_branch.py          # Notice subgraph
├── agents/
│   ├── ca_extraction_agent.py
│   ├── ca_validation_agent.py
│   ├── ca_sql_storage_agent.py
│   ├── ca_embedding_agent.py
│   ├── notice_extraction_agent.py
│   ├── risk_assessment_agent.py
│   ├── notice_validation_agent.py
│   ├── rag_validation_agent.py
│   └── transaction_execution_agent.py
├── tools/
│   ├── pdf_extract_tool.py
│   ├── confidence_check_tool.py
│   ├── neon_read_tool.py
│   ├── neon_insert_tool.py
│   ├── neon_update_tool.py
│   ├── embed_and_store_tool.py
│   ├── rag_query_tool.py
│   ├── r2_upload_tool.py
│   ├── r2_fetch_tool.py
│   ├── calculator_tool.py
│   ├── date_tool.py
│   ├── comparison_tool.py
│   ├── fuzzy_match_tool.py
│   ├── fx_tool.py
│   └── web_search_tool.py
├── db/
│   ├── schema.sql                # all 4 table definitions
│   └── seed.sql                  # 10-15 pre-seeded deals for demo
└── tests/
    └── sample_pdfs/              # sample CA and notice PDFs for testing
```

## Critical Rules — Never Violate
- Never add DELETE to any SQL tool
- Never let LLM do arithmetic — always use `calculator_tool`
- Never let LLM do comparisons — always use `comparison_tool`
- Never let LLM parse or compare dates — always use `date_tool`
- Never store FX results in database — transaction_summary only
- Hard stops always take priority over HIL triggers
- Max 30 tool calls per graph run — enforce via counter in state
- Each agent only accesses its own scoped toolset — never cross-share tools
- All system prompts are in MasterPlan.md Section 15 — use verbatim
- Never commit secrets — all keys in .env only

## Required Environment Variables
```
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
LANGSMITH_API_KEY=
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=loan-servicing-agent
TAVILY_API_KEY=
CLOUDFLARE_R2_ACCESS_KEY_ID=
CLOUDFLARE_R2_SECRET_ACCESS_KEY=
CLOUDFLARE_R2_ENDPOINT_URL=
CLOUDFLARE_R2_BUCKET_NAME=
NEON_DATABASE_URL=
EXCHANGERATE_API_KEY=
```

## Build Order
1. `db/schema.sql` — create all 4 tables (borrower_account, loan_info, firm_balance, transaction_log)
2. `tools/` — implement all 15 tools (see MasterPlan.md Section 16 for specs)
3. `agents/` — implement all 10 agents using system prompts from MasterPlan.md Section 15
4. `graph/` — wire orchestrator, CA subgraph, Notice subgraph with correct state schemas
5. `main.py` — CLI entry point
6. `db/seed.sql` — seed 10-15 demo deals
7. `tests/` — add sample PDFs, smoke test full CA and Notice flows

## Running
```bash
python main.py --pdf path/to/document.pdf
```
View trace at: https://smith.langchain.com under project `loan-servicing-agent`
