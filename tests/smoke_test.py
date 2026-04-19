"""Smoke tests for the loan-servicing-agent.

Usage:
    # 1. Generate sample PDFs first
    python tests/generate_sample_pdfs.py

    # 2. Run smoke tests (requires .env with all keys + seeded DB)
    python tests/smoke_test.py

Each test invokes the full graph end-to-end against the sample PDFs.
Tests verify that the graph completes without uncaught exceptions and
returns the expected doc_type / outcome fields.

NOTE: These are integration smoke tests, not unit tests.
All external services (Neon, R2, OpenAI, Anthropic, Tavily, ExchangeRate-API)
must be live and configured in .env for tests to pass.
"""

import os
import sys
import uuid
import json
import traceback

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "sample_pdfs")

_PASS = "\033[92mPASS\033[0m"
_FAIL = "\033[91mFAIL\033[0m"
_SKIP = "\033[93mSKIP\033[0m"

results: list[dict] = []


def run_test(name: str, pdf_name: str, expected_doc_type: str) -> None:
    """Run one smoke test."""
    from graph.orchestrator import app

    pdf_path = os.path.join(SAMPLE_DIR, pdf_name)
    if not os.path.exists(pdf_path):
        print(f"  [{_SKIP}] {name} — PDF not found: {pdf_path}")
        results.append({"name": name, "status": "skip"})
        return

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "pdf_path": pdf_path,
        "raw_text": "",
        "doc_type": "",
        "r2_url": "",
        "error_message": None,
    }

    try:
        result = app.invoke(initial_state, config=config)
        doc_type = result.get("doc_type", "")
        error = result.get("error_message")

        if error:
            print(f"  [{_FAIL}] {name} — graph returned error: {error}")
            results.append({"name": name, "status": "fail", "reason": error})
        elif doc_type != expected_doc_type:
            msg = f"expected doc_type={expected_doc_type}, got doc_type={doc_type}"
            print(f"  [{_FAIL}] {name} — {msg}")
            results.append({"name": name, "status": "fail", "reason": msg})
        else:
            print(f"  [{_PASS}] {name} — doc_type={doc_type}, thread_id={thread_id}")
            results.append({"name": name, "status": "pass"})

    except Exception as exc:
        tb = traceback.format_exc()
        print(f"  [{_FAIL}] {name} — exception: {exc}")
        print(f"           {tb[:400]}")
        results.append({"name": name, "status": "fail", "reason": str(exc)})


def test_tool_imports() -> None:
    """Verify all 15 tools import without error."""
    name = "Tool imports"
    try:
        from tools.pdf_extract_tool import pdf_extract_tool
        from tools.confidence_check_tool import confidence_check_tool
        from tools.calculator_tool import calculator_tool
        from tools.comparison_tool import comparison_tool
        from tools.date_tool import date_tool
        from tools.neon_read_tool import neon_read_tool
        from tools.neon_insert_tool import neon_insert_tool
        from tools.neon_update_tool import neon_update_tool
        from tools.embed_and_store_tool import embed_and_store_tool
        from tools.rag_query_tool import rag_query_tool
        from tools.r2_upload_tool import r2_upload_tool
        from tools.r2_fetch_tool import r2_fetch_tool
        from tools.fuzzy_match_tool import fuzzy_match_tool
        from tools.fx_tool import fx_tool
        from tools.web_search_tool import web_search_tool
        print(f"  [{_PASS}] {name}")
        results.append({"name": name, "status": "pass"})
    except Exception as exc:
        print(f"  [{_FAIL}] {name} — {exc}")
        results.append({"name": name, "status": "fail", "reason": str(exc)})


def test_agent_imports() -> None:
    """Verify all 9 agents import without error."""
    name = "Agent imports"
    try:
        from agents.ca_extraction_agent import ca_extraction_agent
        from agents.ca_validation_agent import ca_validation_agent
        from agents.ca_sql_storage_agent import ca_sql_storage_agent
        from agents.ca_embedding_agent import ca_embedding_agent
        from agents.notice_extraction_agent import notice_extraction_agent
        from agents.risk_assessment_agent import risk_assessment_agent
        from agents.notice_validation_agent import notice_validation_agent
        from agents.rag_validation_agent import rag_validation_agent
        from agents.transaction_execution_agent import transaction_execution_agent
        print(f"  [{_PASS}] {name}")
        results.append({"name": name, "status": "pass"})
    except Exception as exc:
        print(f"  [{_FAIL}] {name} — {exc}")
        results.append({"name": name, "status": "fail", "reason": str(exc)})


def test_graph_compile() -> None:
    """Verify all three graphs compile without error."""
    name = "Graph compilation"
    try:
        from graph.ca_branch import ca_app
        from graph.notice_branch import notice_app
        from graph.orchestrator import app
        print(f"  [{_PASS}] {name}")
        results.append({"name": name, "status": "pass"})
    except Exception as exc:
        print(f"  [{_FAIL}] {name} — {exc}")
        results.append({"name": name, "status": "fail", "reason": str(exc)})


def test_unit_tools() -> None:
    """Unit-test pure tools that need no external services."""
    name = "Unit: calculator_tool"
    try:
        from tools.calculator_tool import calculator_tool
        r = calculator_tool.invoke({"value_a": 100.0, "value_b": 50.0, "operation": "+"})
        assert r["result"] == 150.0, f"unexpected: {r}"
        r2 = calculator_tool.invoke({"value_a": -42.0, "value_b": 0.0, "operation": "abs"})
        assert r2["result"] == 42.0, f"unexpected: {r2}"
        print(f"  [{_PASS}] {name}")
        results.append({"name": name, "status": "pass"})
    except Exception as exc:
        print(f"  [{_FAIL}] {name} — {exc}")
        results.append({"name": name, "status": "fail", "reason": str(exc)})

    name = "Unit: comparison_tool"
    try:
        from tools.comparison_tool import comparison_tool
        r = comparison_tool.invoke({"value_a": 100.0, "value_b": 50.0, "operator": ">"})
        assert r["result"] is True
        r2 = comparison_tool.invoke({"value_a": "USD", "value_b": "usd", "operator": "="})
        assert r2["result"] is True  # case-insensitive
        print(f"  [{_PASS}] {name}")
        results.append({"name": name, "status": "pass"})
    except Exception as exc:
        print(f"  [{_FAIL}] {name} — {exc}")
        results.append({"name": name, "status": "fail", "reason": str(exc)})

    name = "Unit: date_tool"
    try:
        from tools.date_tool import date_tool
        r = date_tool.invoke({"operation": "today"})
        assert r["result"] and len(r["result"]) == 10  # YYYY-MM-DD
        r2 = date_tool.invoke({"operation": "diff_days", "date_a": "2025-01-01", "date_b": "2025-01-06"})
        assert r2["result"] == 5
        print(f"  [{_PASS}] {name}")
        results.append({"name": name, "status": "pass"})
    except Exception as exc:
        print(f"  [{_FAIL}] {name} — {exc}")
        results.append({"name": name, "status": "fail", "reason": str(exc)})

    name = "Unit: confidence_check_tool"
    try:
        from tools.confidence_check_tool import confidence_check_tool
        r = confidence_check_tool.invoke({
            "field_name": "deal_name",
            "extracted_value": "Demo Alpha",
            "source_snippet": "Facility Name: Demo Alpha Term Loan"
        })
        assert "confidence_score" in r
        assert 0.0 <= r["confidence_score"] <= 1.0
        print(f"  [{_PASS}] {name}")
        results.append({"name": name, "status": "pass"})
    except Exception as exc:
        print(f"  [{_FAIL}] {name} — {exc}")
        results.append({"name": name, "status": "fail", "reason": str(exc)})

    name = "Unit: fuzzy_match_tool"
    try:
        from tools.fuzzy_match_tool import fuzzy_match_tool
        r = fuzzy_match_tool.invoke({
            "query": "Demo Alpha Term Loan",
            "candidates": ["Demo Alpha Term Loan Facility 2025", "Other Deal", "Apex Term"],
            "threshold": 0.8
        })
        assert r["best_match"] is not None
        print(f"  [{_PASS}] {name}")
        results.append({"name": name, "status": "pass"})
    except Exception as exc:
        print(f"  [{_FAIL}] {name} — {exc}")
        results.append({"name": name, "status": "fail", "reason": str(exc)})


def test_pdf_extraction() -> None:
    """Test pdf_extract_tool against a generated sample PDF."""
    name = "Unit: pdf_extract_tool (sample CA)"
    ca_path = os.path.join(SAMPLE_DIR, "sample_ca.pdf")
    if not os.path.exists(ca_path):
        print(f"  [{_SKIP}] {name} — run generate_sample_pdfs.py first")
        results.append({"name": name, "status": "skip"})
        return
    try:
        from tools.pdf_extract_tool import pdf_extract_tool
        r = pdf_extract_tool.invoke({"file_path": ca_path})
        assert r.get("error") is None, f"extraction error: {r.get('error')}"
        assert "CREDIT AGREEMENT" in r["raw_text"]
        assert r["word_count"] > 100
        print(f"  [{_PASS}] {name} — pages={r['page_count']}, words={r['word_count']}")
        results.append({"name": name, "status": "pass"})
    except Exception as exc:
        print(f"  [{_FAIL}] {name} — {exc}")
        results.append({"name": name, "status": "fail", "reason": str(exc)})


def main() -> None:
    print("\n" + "=" * 60)
    print("  Loan Servicing Agent — Smoke Tests")
    print("=" * 60 + "\n")

    print("[ Import & Compile Tests ]")
    test_tool_imports()
    test_agent_imports()
    test_graph_compile()

    print("\n[ Unit Tests (no external services) ]")
    test_unit_tools()
    test_pdf_extraction()

    print("\n[ End-to-End Graph Tests (requires live services) ]")
    run_test("E2E: CA processing",             "sample_ca.pdf",               "CA")
    run_test("E2E: Drawdown notice",           "sample_drawdown_notice.pdf",  "Notice")
    run_test("E2E: Repayment notice",          "sample_repayment_notice.pdf", "Notice")
    run_test("E2E: Interest payment notice",   "sample_interest_notice.pdf",  "Notice")
    run_test("E2E: Fee payment notice",        "sample_fee_notice.pdf",       "Notice")

    # Summary
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    skipped = sum(1 for r in results if r["status"] == "skip")

    print("\n" + "=" * 60)
    print(f"  Results: {passed} passed / {failed} failed / {skipped} skipped")
    print("=" * 60)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
