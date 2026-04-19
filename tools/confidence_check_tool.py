from langchain_core.tools import tool
import re
from rapidfuzz import fuzz


def _score_string(value: str, source_snippet: str) -> float:
    """Compute partial_ratio score for string values."""
    ratio = fuzz.partial_ratio(str(value), source_snippet)
    return min(ratio / 100.0, 1.0)


def _score_numeric(value: float | int, source_snippet: str) -> float:
    """Check if the numeric value appears literally in the source snippet."""
    str_val = str(value)
    # Without trailing zeros for floats (e.g. 1000000.0 -> 1000000)
    alt_val = str(int(value)) if isinstance(value, float) and value == int(value) else None
    # Comma-formatted (e.g. 50000000 -> "50,000,000")
    try:
        comma_val = f"{int(value):,}"
    except (ValueError, TypeError):
        comma_val = None
    if (str_val in source_snippet
            or (alt_val and alt_val in source_snippet)
            or (comma_val and comma_val in source_snippet)):
        return 1.0
    return 0.6


def _score_bool(field_name: str, value: bool, source_snippet: str) -> float:
    """Check if a boolean indicator appears near the field name in the source snippet."""
    bool_indicators = re.compile(
        r"\b(true|false|yes|no|complete|incomplete|active|inactive|enabled|disabled)\b",
        re.IGNORECASE,
    )
    # Normalize field_name: underscores → spaces so "fcc_flag" matches "FCC Flag"
    field_display = field_name.replace("_", " ")
    field_pattern = re.compile(re.escape(field_display), re.IGNORECASE)
    if field_pattern.search(source_snippet) and bool_indicators.search(source_snippet):
        return 0.9
    if bool_indicators.search(source_snippet):
        return 0.7
    return 0.5


def _score_date(source_snippet: str) -> float:
    """Check if a date value appears in the source snippet."""
    iso_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
    date_like_pattern = re.compile(
        r"\b(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+\d{1,2},?\s+\d{4}\b|\b\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}\b",
        re.IGNORECASE,
    )
    if iso_pattern.search(source_snippet):
        return 1.0
    if date_like_pattern.search(source_snippet):
        return 0.7
    return 0.4


@tool
def confidence_check_tool(
    field_name: str,
    extracted_value: object,
    source_snippet: str,
) -> dict:
    """Score extraction confidence for a field value against its source snippet; flag if below 0.75."""
    try:
        # Truncate source_snippet to 500 chars as per spec
        source_snippet = source_snippet[:500]

        # Empty or None value → score 0.0
        if extracted_value is None or extracted_value == "" or extracted_value == []:
            return {
                "confidence_score": 0.0,
                "flag": True,
                "reason": "Extracted value is empty or None.",
            }

        score: float

        # Bool check must come before int/float because bool is a subclass of int in Python
        if isinstance(extracted_value, bool):
            score = _score_bool(field_name, extracted_value, source_snippet)

        elif isinstance(extracted_value, (int, float)):
            score = _score_numeric(extracted_value, source_snippet)

        elif isinstance(extracted_value, str):
            # Detect if the string looks like a date (YYYY-MM-DD or common date patterns)
            iso_date = re.compile(r"^\d{4}-\d{2}-\d{2}$")
            loose_date = re.compile(
                r"^\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}$|"
                r"^(?:January|February|March|April|May|June|July|August|September|"
                r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
                r"\s+\d{1,2},?\s+\d{4}$",
                re.IGNORECASE,
            )
            if iso_date.match(extracted_value.strip()) or loose_date.match(extracted_value.strip()):
                score = _score_date(source_snippet)
            else:
                score = _score_string(extracted_value, source_snippet)

        else:
            # Fallback: convert to string and use string scoring
            score = _score_string(str(extracted_value), source_snippet)

        score = min(score, 1.0)
        flag = score < 0.75

        reason: str | None = None
        if flag:
            reason = (
                f"Confidence score {score:.2f} is below threshold 0.75 for field '{field_name}'. "
                f"Extracted value '{extracted_value}' may not be reliably supported by source snippet."
            )

        return {
            "confidence_score": round(score, 4),
            "flag": flag,
            "reason": reason,
        }

    except Exception as e:
        return {
            "confidence_score": 0.0,
            "flag": True,
            "reason": f"Error during confidence check: {str(e)}",
        }
