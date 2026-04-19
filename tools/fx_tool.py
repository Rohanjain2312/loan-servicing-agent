from langchain_core.tools import tool
from dotenv import load_dotenv
import os
import requests
from datetime import datetime, timezone

load_dotenv(override=True)


@tool
def fx_tool(
    from_currency: str,
    to_currency: str,
    amount: float,
) -> dict:
    """Convert a currency amount to another currency using ExchangeRate-API.

    In this system, to_currency is always "USD". Never stores FX results in the database;
    the result is for transaction_summary use only.

    Args:
        from_currency: ISO 4217 source currency code, e.g. "GBP", "EUR".
        to_currency: ISO 4217 target currency code, typically "USD".
        amount: Amount to convert in from_currency.

    Returns:
        Dict with converted_amount, exchange_rate, rate_timestamp, and error fields.
    """
    try:
        # Short-circuit: same currency, no API call needed
        if from_currency.upper() == to_currency.upper():
            return {
                "converted_amount": round(amount, 2),
                "exchange_rate": 1.0,
                "rate_timestamp": datetime.now(timezone.utc).isoformat(),
                "error": None,
            }

        api_key = os.getenv("EXCHANGERATE_API_KEY")
        if not api_key:
            return {
                "converted_amount": None,
                "exchange_rate": None,
                "rate_timestamp": None,
                "error": "Missing EXCHANGERATE_API_KEY environment variable.",
            }

        url = (
            f"https://v6.exchangerate-api.com/v6/{api_key}"
            f"/pair/{from_currency.upper()}/{to_currency.upper()}/{amount}"
        )

        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            return {
                "converted_amount": None,
                "exchange_rate": None,
                "rate_timestamp": None,
                "error": (
                    f"ExchangeRate-API returned HTTP {response.status_code}: "
                    f"{response.text[:200]}"
                ),
            }

        data = response.json()

        if data.get("result") != "success":
            error_type = data.get("error-type", "unknown error")
            return {
                "converted_amount": None,
                "exchange_rate": None,
                "rate_timestamp": None,
                "error": f"ExchangeRate-API error: {error_type}",
            }

        converted_amount = round(float(data["conversion_result"]), 2)
        exchange_rate = float(data["conversion_rate"])
        rate_timestamp = data.get(
            "time_last_update_utc",
            datetime.now(timezone.utc).isoformat(),
        )

        return {
            "converted_amount": converted_amount,
            "exchange_rate": exchange_rate,
            "rate_timestamp": rate_timestamp,
            "error": None,
        }

    except requests.exceptions.Timeout:
        return {
            "converted_amount": None,
            "exchange_rate": None,
            "rate_timestamp": None,
            "error": "ExchangeRate-API request timed out after 10 seconds.",
        }
    except requests.exceptions.RequestException as e:
        return {
            "converted_amount": None,
            "exchange_rate": None,
            "rate_timestamp": None,
            "error": f"Network error calling ExchangeRate-API: {str(e)}",
        }
    except Exception as e:
        return {
            "converted_amount": None,
            "exchange_rate": None,
            "rate_timestamp": None,
            "error": str(e),
        }
