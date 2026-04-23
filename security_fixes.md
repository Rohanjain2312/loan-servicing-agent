# Security Fixes & Guardrails — Syndicated Loan Agent System

## Purpose

3 mandatory guardrails derived from known agentic AI failure patterns. Each entry covers **what** to add, **where** it goes, and **why** it exists. Claude Code decides implementation details. Read `MasterPlan.md` first — this document extends it, does not replace it.

---

## Fix 1 — Cross-Field Consistency Check (CA Branch)

**Why:** CA PDFs contain the same data point in multiple sections — term sheet at the front, operative clauses in the middle, schedules at the back. The extraction agent may pick the wrong occurrence. Each extracted field may look individually valid while being internally inconsistent with another. This must be caught before anything reaches SQL.

**Where:** New deterministic node `nodes/cross_field_consistency_check.py`, inserted between CA Extraction Agent and CA Validation Agent. Not an LLM call — pure Python comparisons. Any failure triggers `interrupt()` describing which fields conflicted and their values.

**Key behaviour:** Every check is conditional. If the required fields are not present (None or empty), the check is skipped — no interrupt. Checks only fire when there is more than one occurrence of a field to compare, or when a field that is present violates a rule. `consistency_check_passed` and `consistency_check_errors` are always written to state by this node as outputs — they are never inputs.

**Checks to implement:**

| Check ID | Rule | Note |
|---|---|---|
| CC-01 | Extraction agent must extract `committed_amount_summary` (term sheet) and `committed_amount_operative` (operative clause) as two separate fields. If both are present, they must match within 0.01. If match → write `committed_amount = committed_amount_operative` to state. If only one is found → skip comparison, use whichever is present. If both found but mismatch → HIL. | NEW |
| CC-02 | If `tranche_amounts` is present and non-empty: `sum(tranche_amounts)` must equal `committed_amount` within 0.01 → HIL if not. If field absent or empty → skip. | NEW |
| CC-03 | maturity > origination check | ALREADY IN MASTERPLAN Check 13 — do not re-implement |
| CC-04 | If both `maturity_date` and `origination_date` are present: difference must be > 30 days → HIL if not. Use `origination_date` (MasterPlan field name). | NEW |
| CC-05 | Margin range check | ALREADY IN MASTERPLAN Checks 18–19 — do not re-implement |
| CC-06 | If both `committed_amount_currency` and `currency` are present: must match after uppercase normalisation → HIL if not. | NEW |
| CC-07 | If `min_drawdown_amount` is present: must be < `committed_amount` → HIL if not. If absent → skip. | NEW |
| CC-08 | If `drawdown_notice_days` is present: must be a positive integer ≥ 1 → HIL if not. If absent → skip. | NEW |
| CC-09 | committed_amount > 0 check | ALREADY IN MASTERPLAN Check 15 — do not re-implement |
| CC-10 | Confidence threshold check | ALREADY IN MASTERPLAN Check 20 at threshold 0.75 — do not re-implement |

**State fields to add to `CAWorkflowState`:** `committed_amount_summary`, `committed_amount_operative`, `tranche_amounts`, `consistency_check_passed`, `consistency_check_errors`.

---

## Fix 2 — Idempotent SQL Writes

**Why:** If a notice is submitted twice, or the orchestrator retries a node after a transient failure, the same record must not be written to the database twice. Without unique constraints, duplicate transaction records corrupt balance calculations and the audit trail. This must be structurally impossible at the database level, not just guarded by application logic.

**Note on retry limits:** Max tool call limit (30) and execution timeouts are already defined in MasterPlan guardrails. Do not re-implement those here.

**Where:** Add unique constraints to `db/schema.sql`. Update insert logic in `tools/neon_insert_tool.py` and `tools/neon_update_tool.py` to handle conflicts explicitly.

**What to add:**

`deals` table — add unique constraint on `deal_name`. All inserts must use `ON CONFLICT DO NOTHING RETURNING id`. If a conflict is detected (deal already exists), do not silently overwrite — trigger `interrupt()` surfacing the existing deal ID to the human for review before proceeding.

`notices` table — add unique constraint on `(deal_id, notice_type, notice_date, requested_amount)`. Same insert pattern. Conflict → `interrupt()` with duplicate warning showing the matching existing record.

`transactions` table — add unique constraint on `notice_id`. One notice produces exactly one transaction record, ever. Before the Transaction Execution Agent writes anything, check whether a transaction already exists for this `notice_id`. If yes → hard stop, `interrupt()`. Never create a second record.

---

## Fix 3 — Pydantic Schema Validation at Every Agent Boundary

**Why:** Claude Sonnet and GPT-4o-mini outputs flow into shared LangGraph state and are read by downstream agents. Type mismatches — a string where a date is expected, a float where an int is expected — often fail silently in Python, producing wrong downstream results with no error raised. As the project evolves and fields change, agents break without warning.

**Where:** New file `schemas.py` in project root. New node `nodes/schema_validation_node.py`. Inserted after every agent that produces structured output.

**What to build:**

`schemas.py` is the single source of truth for all inter-agent data structures. Define Pydantic models for: `ExtractedCAFields`, `ExtractedNoticeFields`, `RAGCheckResult`, `ValidationResult`, `TransactionRecord`. No agent defines its own ad-hoc dict — all import from `schemas.py`.

Add a `SCHEMA_VERSION` constant. Bump it with a comment every time any schema changes.

Validators to include — **only those not already covered by MasterPlan:**
- All currency fields: must be valid uppercase ISO 4217 code
- `drawdown_notice_days`: must be ≥ 1
- `value_date` in notices: must not be before `notice_date`
- `RAGCheckResult.confidence_score`: must be between 0.0 and 1.0
- `RAGCheckResult.agent_conclusion`: must be one of `PERMITTED`, `BLOCKED`, `INSUFFICIENT_EVIDENCE`

Do NOT add validators for: margin range, committed_amount > 0, maturity > origination — all already in MasterPlan CA Validation Agent. Duplicating them creates conflicting checks.

`schema_validation_node` validates a named state field against its expected schema. On failure → `interrupt()` with a description of exactly which fields failed and why.

Insert schema validation nodes at:
- After CA Extraction Agent → validate `ExtractedCAFields`
- After CA Validation Agent → validate `ValidationResult`
- After Notice Extraction Agent → validate `ExtractedNoticeFields`
- After RAG Validation Agent → validate each `RAGCheckResult` in the results list
- After Notice Validation Agent → validate `ValidationResult`
- After Transaction Execution Agent → validate `TransactionRecord`

Both `CAWorkflowState` and `NoticeWorkflowState` must be typed (TypedDict or dataclass) — not plain dicts. Add `schema_validation_passed: bool` and `schema_validation_errors: list[str]` to both.

---

## Execution Time Note

Max execution time per agent node is reduced to **2 minutes** (down from 5 minutes in MasterPlan). MasterPlan will be updated post-implementation and testing. Total graph execution time (10 minutes, excluding HIL wait) remains unchanged.

---

## Files to Create / Modify

| Action | File |
|---|---|
| CREATE | `schemas.py` |
| CREATE | `nodes/cross_field_consistency_check.py` |
| CREATE | `nodes/schema_validation_node.py` |
| MODIFY | `tools/neon_insert_tool.py` — conflict handling on all inserts |
| MODIFY | `tools/neon_update_tool.py` — pre-check for existing transaction before execution |
| MODIFY | `graph/ca_branch.py` — insert consistency check node and schema validation nodes |
| MODIFY | `graph/notice_branch.py` — insert schema validation nodes |
| MODIFY | `db/schema.sql` — unique constraints on deals, notices, transactions |

## Relationship to MasterPlan.md

This document extends MasterPlan.md — it does not replace it. Read MasterPlan.md first. Do not remove or override anything in MasterPlan.md unless explicitly stated here.
