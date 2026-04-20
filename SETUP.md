# Setup Guide

Complete step-by-step instructions to run the Loan Servicing Agent on your machine.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | `python --version` to check |
| Git | Any | For cloning the repo |
| pip | Latest | `pip install --upgrade pip` |

You will also need accounts on **six external services**. All have free tiers that are sufficient for running this project:

| Service | Free Tier | Used For |
|---------|-----------|----------|
| [Anthropic](https://console.anthropic.com) | Pay-per-use | Claude Sonnet + Haiku (orchestrator, agents) |
| [OpenAI](https://platform.openai.com) | Pay-per-use | GPT-4o-mini (extraction agents) + text-embedding-3-small |
| [LangSmith](https://smith.langchain.com) | Free developer tier | Tracing + HIL Studio interface |
| [Neon](https://neon.tech) | Free tier (0.5 GB) | PostgreSQL + pgvector |
| [Cloudflare R2](https://dash.cloudflare.com) | 10 GB free/month | PDF storage |
| [Tavily](https://tavily.com) | 1,000 searches/month free | Web search (risk assessment) |
| [ExchangeRate-API](https://www.exchangerate-api.com) | 1,500 req/month free | FX conversion |

---

## Step 1 — Clone the Repository

```bash
git clone https://github.com/Rohanjain2312/loan-servicing-agent.git
cd loan-servicing-agent
```

---

## Step 2 — Create a Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows
```

---

## Step 3 — Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This installs: LangGraph, LangChain, LangSmith, Anthropic SDK, OpenAI SDK, PyMuPDF, psycopg2, pgvector, boto3, rapidfuzz, tavily-python, python-dateutil, requests, python-dotenv.

---

## Step 4 — Get Your API Keys

### 4.1 Anthropic API Key
1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Create an account and navigate to **API Keys**
3. Click **Create Key** — copy the key starting with `sk-ant-...`

### 4.2 OpenAI API Key
1. Go to [platform.openai.com](https://platform.openai.com)
2. Navigate to **API Keys** → **Create new secret key**
3. Copy the key starting with `sk-...`

### 4.3 LangSmith API Key
1. Go to [smith.langchain.com](https://smith.langchain.com)
2. Sign up / log in
3. Go to **Settings** → **API Keys** → **Create API Key**
4. Copy the key

### 4.4 Tavily API Key
1. Go to [tavily.com](https://tavily.com)
2. Sign up and navigate to the dashboard
3. Your API key is shown on the home page — copy it

### 4.5 ExchangeRate-API Key
1. Go to [exchangerate-api.com](https://www.exchangerate-api.com)
2. Click **Get Free Key** — no credit card required
3. Enter your email, confirm it, and copy the API key from your dashboard

---

## Step 5 — Set Up Neon (PostgreSQL + pgvector)

Neon is a serverless PostgreSQL provider that supports pgvector natively.

1. Go to [neon.tech](https://neon.tech) and sign up
2. Click **New Project** → give it a name (e.g. `loan-servicing-agent`)
3. Select a region close to you
4. Once created, go to **Connection Details**
5. Copy the **Connection String** — it looks like:
   ```
   postgresql://user:password@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
   This is your `NEON_DATABASE_URL`.

### 5.1 Apply the Schema

Using the Neon SQL Editor (in the dashboard) or `psql`:

```bash
# Via psql (requires psql installed):
psql "$NEON_DATABASE_URL" -f db/schema.sql
```

Or paste the contents of `db/schema.sql` into the Neon SQL Editor and run it.

This creates 5 tables: `borrower_account`, `firm_balance`, `loan_info`, `transaction_log`, `ca_embeddings` (pgvector).

### 5.2 Seed Demo Data

```bash
psql "$NEON_DATABASE_URL" -f db/seed.sql
```

This inserts 10–15 pre-built deals covering various notice scenarios (drawdown, interest, repayment, fee) for testing.

---

## Step 6 — Set Up Cloudflare R2

R2 is Cloudflare's S3-compatible object storage with no egress fees.

1. Go to [dash.cloudflare.com](https://dash.cloudflare.com) and sign in (free account)
2. In the sidebar, click **R2 Object Storage**
3. Click **Create bucket** — name it (e.g. `loan-servicing-pdfs`). This is your `CLOUDFLARE_R2_BUCKET_NAME`.
4. In R2 settings, note your **Account ID** (visible in the URL bar: `dash.cloudflare.com/<account-id>/r2`)
5. Your endpoint URL is: `https://<account-id>.r2.cloudflarestorage.com` — this is your `CLOUDFLARE_R2_ENDPOINT_URL`

### 6.1 Create an R2 API Token

1. In R2, click **Manage R2 API Tokens** → **Create API Token**
2. Set **Permissions** to **Object Read & Write**
3. Under **Specify bucket**, select your bucket
4. Click **Create API Token**
5. Copy the **Access Key ID** (`CLOUDFLARE_R2_ACCESS_KEY_ID`) and **Secret Access Key** (`CLOUDFLARE_R2_SECRET_ACCESS_KEY`) — the secret is only shown once

---

## Step 7 — Create the `.env` File

In the project root, create a file named `.env` (never commit this):

```bash
cp .env.example .env
```

Open `.env` and fill in all values:

```env
# LLM providers
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# LangSmith tracing
LANGSMITH_API_KEY=ls__...
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=loan-servicing-agent

# Web search
TAVILY_API_KEY=tvly-...

# Cloudflare R2
CLOUDFLARE_R2_ACCESS_KEY_ID=...
CLOUDFLARE_R2_SECRET_ACCESS_KEY=...
CLOUDFLARE_R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
CLOUDFLARE_R2_BUCKET_NAME=loan-servicing-pdfs

# Neon PostgreSQL
NEON_DATABASE_URL=postgresql://user:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require

# FX conversion
EXCHANGERATE_API_KEY=...
```

---

## Step 8 — Verify the Setup

Run a quick connectivity check by testing each service:

```bash
# Verify Python env
python -c "import langchain, langgraph, anthropic, openai, fitz, psycopg2; print('All imports OK')"

# Verify Neon connection
python -c "
import psycopg2, os
from dotenv import load_dotenv
load_dotenv()
conn = psycopg2.connect(os.getenv('NEON_DATABASE_URL'))
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM loan_info')
print(f'loan_info rows: {cur.fetchone()[0]}')
conn.close()
"

# Verify R2 connection
python -c "
import boto3, os
from dotenv import load_dotenv
load_dotenv()
s3 = boto3.client('s3',
    endpoint_url=os.getenv('CLOUDFLARE_R2_ENDPOINT_URL'),
    aws_access_key_id=os.getenv('CLOUDFLARE_R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('CLOUDFLARE_R2_SECRET_ACCESS_KEY'),
)
print(s3.list_buckets())
"
```

---

## Step 9 — Run the Agent

### Option A — CLI

```bash
python main.py --pdf /path/to/your/document.pdf
```

On first run, a LangSmith trace link is printed in the terminal. Open it to see the full agent trace.

To resume a paused run (after a HIL interrupt):

```bash
python main.py --pdf /path/to/your/document.pdf --thread-id <thread-id-from-previous-run>
```

### Option B — LangSmith Studio (recommended for HIL)

LangSmith Studio is the primary interface for this project — it shows the full graph, live traces, and lets you approve/deny HIL interrupts visually.

1. Install the LangGraph CLI:
   ```bash
   pip install langgraph-cli
   ```
2. Start the local LangGraph server:
   ```bash
   langgraph dev
   ```
3. Open [LangSmith Studio](https://smith.langchain.com) → select your project → click **Open in Studio**
4. In Studio, click **+** to start a new run
5. Set `pdf_path` to the absolute path of your PDF
6. Click **Submit** — the graph runs and pauses at HIL nodes waiting for your approval

---

## Step 10 — Try It With Sample PDFs

Sample PDFs are in `tests/sample_pdfs/`. They cover:

| File | Type | Scenario |
|------|------|----------|
| `CA_*.pdf` | Credit Agreement | New deal onboarding |
| `Notice_Drawdown_*.pdf` | Drawdown notice | Funds requested |
| `Notice_Repayment_*.pdf` | Repayment notice | Principal repayment |
| `Notice_Interest_*.pdf` | Interest payment | Interest with ACT/360 check |
| `Notice_Interest_Mismatch_*.pdf` | Interest payment | Triggers interest amount HIL |
| `Notice_Fee_*.pdf` | Fee payment | Commitment fee |

```bash
# Process a CA
python main.py --pdf tests/sample_pdfs/CA_TechCorp_Term_Loan.pdf

# Process a drawdown notice (will trigger HIL in Studio)
python main.py --pdf tests/sample_pdfs/Notice_Drawdown_Deal1.pdf
```

---

## Troubleshooting

**`ImportError: No module named 'fitz'`**
→ Run `pip install pymupdf`

**`psycopg2.OperationalError: SSL connection required`**
→ Make sure `?sslmode=require` is at the end of your `NEON_DATABASE_URL`

**`botocore.exceptions.NoCredentialsError`**
→ Double-check `CLOUDFLARE_R2_ACCESS_KEY_ID` and `CLOUDFLARE_R2_SECRET_ACCESS_KEY` in `.env`

**`risk_meter field is required` on CA insert**
→ The CA PDF doesn't mention risk level. The agent will automatically web-search the borrower to classify it. Ensure `TAVILY_API_KEY` is set.

**HIL interrupt not resuming in Studio**
→ All `interrupt()` calls live at the parent orchestrator level — subgraphs are pure compute. If you're running CLI, pass `--thread-id` from the previous run.

**LangSmith trace not appearing**
→ Confirm `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` are in `.env` and the project name matches `LANGSMITH_PROJECT`.
