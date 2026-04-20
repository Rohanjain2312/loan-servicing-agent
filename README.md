# Loan Servicing Agent

A production-grade multi-agent AI system for processing syndicated loan documents. Drop in a Credit Agreement or Notice PDF — the system extracts, validates, and executes the appropriate action end-to-end, with human-in-the-loop checkpoints at every risk decision.

Built with LangGraph + LangSmith Studio, backed by Neon PostgreSQL (+ pgvector) and Cloudflare R2.

---

## What It Does

**Credit Agreement (CA)** — onboards a new loan deal:
- Extracts 19 structured fields (borrower, amounts, rates, dates, KYC)
- Validates all fields; routes low-confidence extractions to human review
- Stores deal in SQL, generates embeddings for RAG-based clause retrieval

**Notice** — processes lifecycle events (Drawdown, Repayment, Interest Payment, Fee Payment):
- Matches notice to an existing deal via fuzzy name matching
- Runs live web search to detect borrower risk escalation
- Validates against SQL records + CA clause embeddings (RAG)
- Pauses for human approval on risk flags, validation anomalies, and all drawdowns
- Executes transaction: updates funded amount, firm balance, and audit log

---

## Architecture

```
PDF Input
   │
   ▼
Orchestrator (Claude Sonnet)
   ├─ CA path ──→ [Extract → Validate] → [Confidence HIL?] → [SQL Storage → Embedding]
   └─ Notice path ──→ [Extract → Risk Assessment → Validate ∥ RAG] → [HIL?] → [Execute]
```

Ten specialized agents, each with a scoped toolset. All Human-in-the-Loop interrupts fire at the top-level orchestrator so LangSmith Studio Resume works correctly.

> For full architecture details, state schemas, agent system prompts, and tool specs — see [MasterPlan.md](MasterPlan.md).

---

## Key Features

- **Structured extraction** — 19 CA fields and 4 notice-type-specific templates; GPT-4o-mini follows per-type output formats to avoid field omission
- **Confidence-gated HIL** — CA fields extracted with < 0.75 confidence surface exact source text + agent inference to a human reviewer before storage
- **ACT/360 interest validation** — system-calculated interest uses the correct day-count convention (`principal × rate/100 × period_days/360`) with a $30 tolerance band
- **Risk escalation** — Tavily web search on every notice; any Low→High or Medium→High escalation triggers HIL with news summary and reasoning
- **RAG clause checks** — 4 CA clause checks (conditions precedent, permitted purpose, notice mechanics, repayment conditions) using hybrid pgvector + full-text retrieval
- **Null risk_meter fallback** — if a CA omits a risk rating, the agent web-searches the borrower and classifies before inserting
- **Append-only audit log** — every notice creates a `transaction_log` row with HIL triggers, decisions, and final outcome; no deletes anywhere

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent framework | LangGraph |
| Observability + HIL | LangSmith Studio |
| Orchestrator | Claude Sonnet (`claude-sonnet-4-5`) |
| Sub-agents | GPT-4o-mini (extraction) · Claude Haiku (validation, storage, execution) |
| Database | Neon PostgreSQL + pgvector |
| PDF storage | Cloudflare R2 |
| PDF parsing | PyMuPDF |
| Web search | Tavily |
| Fuzzy matching | rapidfuzz |
| FX rates | ExchangeRate-API |

---

## Quick Start

```bash
git clone https://github.com/Rohanjain2312/loan-servicing-agent.git
cd loan-servicing-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your API keys
```

For the full setup — Neon DB, Cloudflare R2, LangSmith, all API keys — see **[SETUP.md](SETUP.md)**.

---

## Human-in-the-Loop

HIL interrupts surface in **LangSmith Studio** as interactive pause points. Reviewers see the full context and click Approve or Deny.

| Trigger | What's Shown |
|---------|-------------|
| CA low-confidence field | Agent's inference · exact CA source text · confidence score |
| Risk escalated to High | News summary · reasoning · current vs new risk level |
| Validation anomaly (KYC, FCC, balance, rate, interest) | Full calculation breakdown with both notice and system values |
| RAG clause check | Exact CA clause text · notice content · LLM explanation |
| Drawdown notice | Drawdown details · available amount · deal state |

---

## Running

```bash
# CLI
python main.py --pdf /path/to/document.pdf

# Resume after HIL pause
python main.py --pdf /path/to/document.pdf --thread-id <thread-id>

# LangGraph Studio (recommended)
langgraph dev
```

Trace link is printed on startup. Every run is fully observable in LangSmith.

---

## Project Structure

```
loan-servicing-agent/
├── main.py                    # CLI entry point
├── graph/
│   ├── orchestrator.py        # Main graph + all HIL nodes
│   ├── ca_branch.py           # CA subgraph (extract + validate)
│   └── notice_branch.py       # Notice subgraph (extract + risk + validate)
├── agents/                    # 9 specialized agents
├── tools/                     # 15 tools (SQL, R2, RAG, calc, date, FX, search...)
├── db/
│   ├── schema.sql             # 5 tables including pgvector
│   └── seed.sql               # 10–15 seeded demo deals
├── tests/sample_pdfs/         # Sample CA and Notice PDFs
├── MasterPlan.md              # Full design reference
└── SETUP.md                   # Setup guide
```

---

## License

MIT
