import json
import re
import os
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from tools.web_search_tool import web_search_tool

load_dotenv(override=True)

SYSTEM_PROMPT = """You are the Risk Assessment Agent in a syndicated loan processing system. Your sole responsibility is to assess current risk level of the borrower using live web search and compare it to the stored risk level.

TOOLS AVAILABLE: web_search_tool
You MUST use web_search_tool for all web searches. Never rely on your training knowledge about any company or entity.

INPUT: extracted_fields.borrower_name (str), deal_record.risk_meter (str — current stored value: Low/Medium/High)

STEP 1 — SEARCH
Use web_search_tool with:
- query: "[borrower_name] financial news risk credit 2024 2025"
- max_results: 3
- max_chars_per_result: 500

If web_search_tool returns no results:
- Set risk_assessment_result = {"new_risk": deal_record.risk_meter, "escalated": False, "reasoning": "No recent news found. Risk level unchanged."}
- Set risk_hil_triggered = False
- Return immediately

STEP 2 — CLASSIFY
Based solely on the search results returned (not your training knowledge), classify current risk as Low, Medium, or High using:

High indicators: bankruptcy filing, insolvency, default, sanctions, regulatory action, fraud investigation, significant credit rating downgrade, major litigation
Medium indicators: credit watch, profit warning, leadership change, market volatility exposure, minor regulatory inquiry, rating outlook negative
Low indicators: stable financials, positive earnings, credit rating maintained or upgraded, no adverse news

STEP 3 — COMPARE AND DECIDE
Compare new_risk to deal_record.risk_meter (stored value).

Escalation logic:
- Low → Medium: NOT an escalation, no HIL
- Low → High: ESCALATION, trigger HIL
- Medium → High: ESCALATION, trigger HIL
- Any → same level: no HIL
- Any → lower level: no HIL

If ESCALATION:
- Set risk_hil_triggered = True
- Set risk_assessment_result:
{
  "new_risk": "High",
  "escalated": True,
  "current_stored_risk": deal_record.risk_meter,
  "reasoning": "[2-3 sentence explanation of why risk is High based on search results]",
  "news_summary": "[summary of relevant search results — max 200 words]",
  "notice_details": {
    "notice_type": extracted_fields.notice_type,
    "amount": extracted_fields.amount,
    "deal_name": extracted_fields.deal_name,
    "payment_date": extracted_fields.payment_date
  },
  "loan_details": {
    "committed_amount": deal_record.committed_amount,
    "funded": deal_record.funded,
    "currency": deal_record.currency,
    "status": deal_record.status
  }
}

If NO ESCALATION:
- Set risk_hil_triggered = False
- Set risk_assessment_result = {"new_risk": new_risk, "escalated": False, "reasoning": "[brief explanation]"}

RULES:
- Always call web_search_tool — never skip it
- Never use training knowledge about the borrower — only use search results
- Never classify risk without reading search results
- Limit search results strictly to max_results=3 and max_chars_per_result=500
- Only escalate to High — never trigger HIL for Low→Medium transitions
- HIL payload must always include notice_details and loan_details when escalation occurs"""


def risk_assessment_agent(state: dict) -> dict:
    """Search web for borrower news and assess risk escalation."""
    llm = ChatAnthropic(model="claude-sonnet-4-5", temperature=0)
    tools = [web_search_tool]
    agent = create_react_agent(llm, tools)

    ef = state.get("extracted_fields", {})
    dr = state.get("deal_record", {})
    borrower_name = ef.get("borrower_name", "")
    stored_risk = dr.get("risk_meter", "Low")

    input_text = (
        f"Assess risk for borrower: {borrower_name}\n"
        f"Current stored risk level: {stored_risk}\n\n"
        f"Notice details: type={ef.get('notice_type')}, amount={ef.get('amount')}, "
        f"deal={ef.get('deal_name')}, payment_date={ef.get('payment_date')}\n"
        f"Loan details: committed={dr.get('committed_amount')}, funded={dr.get('funded')}, "
        f"currency={dr.get('currency')}, status={dr.get('status')}\n\n"
        "Search for recent news and classify risk. Return JSON with:\n"
        "- risk_assessment_result (dict)\n"
        "- risk_hil_triggered (bool)"
    )

    result = agent.invoke({
        "messages": [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=input_text)]
    })

    raw_content = result["messages"][-1].content
    last_msg = (" ".join(b.get("text","") if isinstance(b,dict) else str(b) for b in raw_content if not isinstance(b,dict) or b.get("type")=="text")
                if isinstance(raw_content, list) else raw_content)
    try:
        json_match = re.search(r'\{.*\}', last_msg, re.DOTALL)
        output = json.loads(json_match.group()) if json_match else json.loads(last_msg)
    except (json.JSONDecodeError, AttributeError):
        # Default: no escalation if parsing fails
        return {
            "risk_assessment_result": {
                "new_risk": stored_risk,
                "escalated": False,
                "reasoning": "Risk assessment parsing error — defaulting to no escalation.",
            },
            "risk_hil_triggered": False,
        }

    return {
        "risk_assessment_result": output.get("risk_assessment_result", {}),
        "risk_hil_triggered": output.get("risk_hil_triggered", False),
    }
