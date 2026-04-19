from langchain_core.tools import tool
from rapidfuzz import process as fuzz_process


@tool
def fuzzy_match_tool(
    query: str,
    candidates: list[str],
    threshold: float = 0.8,
) -> dict:
    """Fuzzy-match a query string against a list of candidate strings.

    Uses rapidfuzz for efficient fuzzy matching. Scores are normalized to 0.0–1.0.

    Args:
        query: The string to match, e.g. a deal name extracted from a notice.
        candidates: List of strings to match against, e.g. all deal names in loan_info.
        threshold: Minimum confidence (0.0–1.0) for a result to be returned as best_match.
                   Defaults to 0.8.

    Returns:
        Dict with best_match, confidence, all_matches (scores >= 0.5), and error fields.
    """
    try:
        if not candidates:
            return {
                "best_match": None,
                "confidence": 0.0,
                "all_matches": [],
                "error": "Candidates list is empty.",
            }

        # extractOne returns (match, score, index) with score in 0–100
        best_result = fuzz_process.extractOne(query, candidates)

        if best_result is None:
            return {
                "best_match": None,
                "confidence": 0.0,
                "all_matches": [],
                "error": None,
            }

        best_match_str, best_score_raw, _ = best_result
        best_confidence = best_score_raw / 100.0

        # Only return best_match if it meets the threshold
        best_match = best_match_str if best_confidence >= threshold else None

        # extract returns list of (match, score, index) with score_cutoff applied (0–100 scale)
        all_results_raw = fuzz_process.extract(
            query, candidates, score_cutoff=50  # 50 on 0–100 scale → 0.5 normalized
        )

        all_matches = sorted(
            [
                {"candidate": match_str, "score": round(score_raw / 100.0, 4)}
                for match_str, score_raw, _ in all_results_raw
            ],
            key=lambda x: x["score"],
            reverse=True,
        )

        return {
            "best_match": best_match,
            "confidence": round(best_confidence, 4),
            "all_matches": all_matches,
            "error": None,
        }

    except Exception as e:
        return {
            "best_match": None,
            "confidence": 0.0,
            "all_matches": [],
            "error": str(e),
        }
