from langchain_core.tools import tool
from dotenv import load_dotenv
import os
from tavily import TavilyClient

load_dotenv(override=True)


@tool
def web_search_tool(
    query: str,
    max_results: int = 3,
    max_chars_per_result: int = 500,
) -> dict:
    """Search the web using Tavily and return structured results.

    Used exclusively by the Risk Assessment Agent for market/regulatory lookups.
    max_results and max_chars_per_result are enforced at call time per system constraints.

    Args:
        query: The search query string.
        max_results: Number of results to return. Must always be 3.
        max_chars_per_result: Max characters per result snippet. Must always be 500.

    Returns:
        Dict with results (list of dicts), result_count, and error fields.
    """
    # Enforce system-level constraints regardless of caller input
    max_results = 3
    max_chars_per_result = 500

    try:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return {
                "results": [],
                "result_count": 0,
                "error": "Missing TAVILY_API_KEY environment variable.",
            }

        client = TavilyClient(api_key=api_key)
        response = client.search(query=query, max_results=max_results)

        raw_results = response.get("results", [])
        parsed_results = []

        for item in raw_results:
            snippet_raw = item.get("content", "") or ""
            snippet = snippet_raw[:max_chars_per_result]

            parsed_results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": snippet,
                    "published_date": item.get("published_date", None),
                }
            )

        return {
            "results": parsed_results,
            "result_count": len(parsed_results),
            "error": None,
        }

    except Exception as e:
        return {
            "results": [],
            "result_count": 0,
            "error": str(e),
        }
