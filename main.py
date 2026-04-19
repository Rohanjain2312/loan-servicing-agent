"""Entry point: python main.py --pdf path/to/document.pdf"""

import argparse
import os
import sys
import uuid
from dotenv import load_dotenv

load_dotenv(override=True)

# LangSmith tracing — must be set before importing LangGraph
os.environ.setdefault("LANGSMITH_TRACING", os.getenv("LANGSMITH_TRACING", "true"))
os.environ.setdefault("LANGSMITH_PROJECT", os.getenv("LANGSMITH_PROJECT", "loan-servicing-agent"))

from graph.orchestrator import get_cli_app
app = get_cli_app()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Loan Servicing Agent — processes CA and Notice PDFs"
    )
    parser.add_argument(
        "--pdf",
        required=True,
        help="Absolute or relative path to the PDF file to process",
    )
    parser.add_argument(
        "--thread-id",
        default=None,
        help="Optional thread ID for resuming a paused (HIL) run. "
             "If omitted, a new thread ID is generated.",
    )
    args = parser.parse_args()

    pdf_path = os.path.abspath(args.pdf)
    if not os.path.exists(pdf_path):
        print(f"ERROR: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    thread_id = args.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print(f"Starting loan-servicing-agent")
    print(f"  PDF:       {pdf_path}")
    print(f"  Thread ID: {thread_id}")
    print(f"  LangSmith: https://smith.langchain.com/projects/{os.getenv('LANGSMITH_PROJECT', 'loan-servicing-agent')}")
    print()

    initial_state = {
        "pdf_path": pdf_path,
        "raw_text": "",
        "doc_type": "",
        "r2_url": "",
        "error_message": None,
    }

    try:
        result = app.invoke(initial_state, config=config)
    except Exception as exc:
        # Graph raised — could be an unhandled HIL interrupt surfaced to caller
        print(f"\nGraph raised exception: {exc}", file=sys.stderr)
        print(f"If this was a HIL interrupt, resume with: python main.py --pdf {pdf_path} --thread-id {thread_id}")
        sys.exit(1)

    print()
    if result.get("error_message"):
        print(f"OUTCOME: FAILED — {result['error_message']}")
        sys.exit(1)
    else:
        print(f"OUTCOME: SUCCESS — doc_type={result.get('doc_type')}")


if __name__ == "__main__":
    main()
