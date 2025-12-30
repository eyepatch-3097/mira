import os
import json
from typing import Dict, Any

from agents.services.openai_client import get_openai_client

ROUTES = {"COMPANY_QA", "REACH_OUT", "DOC_LOOKUP", "SMALLTALK", "OUT_OF_SCOPE"}

def _safe_json(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(raw)
    except Exception:
        return {}

def decide_route(*, agent_name: str, agent_description: str, user_message: str) -> Dict[str, Any]:
    """
    Returns dict:
    {
      "route": one of ROUTES,
      "retrieval_roles": [ ... ],
      "retrieval_query": "short",
      "should_suggest_pages": bool,
      "reason": "short"
    }
    """
    client = get_openai_client()

    # NOTE: json mode requirement: "json" must appear in prompt
    instructions = (
        "You are a decision router for a website chatbot.\n"
        "Return STRICT json only.\n\n"
        "Decide ONE route from:\n"
        "- COMPANY_QA: user asks about company/services or describes a business problem we can help solve\n"
        "- REACH_OUT: user asks to contact/book a call/demo/speak to someone/connect\n"
        "- DOC_LOOKUP: user asks for a specific document/file/report/sheet or named info likely in docs\n"
        "- SMALLTALK: greeting/thanks/pleasantries\n"
        "- OUT_OF_SCOPE: unrelated to this brand or its sources\n\n"
        "Output json with keys:\n"
        "- route\n"
        "- retrieval_roles: subset of [website_guidance, support_faq, contact_data, document_referral]\n"
        "- retrieval_query: short search query for retrieval\n"
        "- should_suggest_pages: boolean\n"
        "- reason: short explanation\n\n"
        "Important policy:\n"
        "- If user asks to reach out/contact, ALWAYS choose REACH_OUT.\n"
        "- If user wants a document, choose DOC_LOOKUP.\n"
        "- If user asks unrelated trivia, choose OUT_OF_SCOPE.\n"
    )

    schema = {
        "route": "COMPANY_QA",
        "retrieval_roles": ["website_guidance"],
        "retrieval_query": "short query",
        "should_suggest_pages": True,
        "reason": "short"
    }

    payload = {
        "json": True,
        "agent": {"name": agent_name, "description": agent_description},
        "user_message": user_message,
        "output_schema": schema,
    }

    resp = client.responses.create(
        model=os.getenv("OPENAI_DECISION_MODEL", "gpt-5-nano"),
        instructions=instructions,
        input="json request:\n" + json.dumps(payload),
        text={"format": {"type": "json_object"}},
    )

    raw = (getattr(resp, "output_text", "") or "").strip()
    data = _safe_json(raw)

    route = (data.get("route") or "").strip()
    if route not in ROUTES:
        # Only safe fallback; no keyword routing
        route = "OUT_OF_SCOPE"

    roles = data.get("retrieval_roles") or []
    roles = [r for r in roles if r in {"website_guidance", "support_faq", "contact_data", "document_referral"}]

    rq = (data.get("retrieval_query") or user_message).strip()[:160]
    should_pages = bool(data.get("should_suggest_pages"))
    reason = (data.get("reason") or "")[:180]

    return {
        "route": route,
        "retrieval_roles": roles,
        "retrieval_query": rq,
        "should_suggest_pages": should_pages,
        "reason": reason,
    }
