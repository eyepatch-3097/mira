# agents/services/router.py
import os
import json
import re
from typing import Any, Dict, List, Optional
from openai import OpenAI
from agents.services.openai_client import get_openai_client

client = None


# Keep your existing intent set, but add GREETING explicitly
ALLOWED_INTENTS = [
    "GREETING",
    "NAVIGATE_PAGE",
    "PRODUCT_DISCOVERY",
    "SUPPORT_FAQ",
    "CONTACT_LOOKUP",
    "DOC_REQUEST",
    "LEAD_GEN",
    "SMALLTALK",
    "UNKNOWN",
]

INTENT_TO_ROLES = {
    "GREETING": [],
    "NAVIGATE_PAGE": ["website_guidance"],
    "PRODUCT_DISCOVERY": ["website_guidance"],
    "SUPPORT_FAQ": ["support_faq"],
    "CONTACT_LOOKUP": ["contact_data"],
    "DOC_REQUEST": ["document_referral"],
    "LEAD_GEN": ["website_guidance", "support_faq"],  # optional enrichment
    "SMALLTALK": [],
    "UNKNOWN": [],
}


GATED_INTENTS = {"DOC_REQUEST", "LEAD_GEN"}

def _minimal_fallback(question: str, max_intents: int) -> List[Dict[str, Any]]:
    q = (question or "").strip()
    return [{
        "type": "UNKNOWN",
        "confidence": 0.01,
        "query": q[:140] or "unknown",
        "roles": [],
        "requires_gating": False,
        "needs_clarification": True,
        "clarifying_question": "What can I help with—navigation, products, support/policies, contact info, or documents?",
    }][:max_intents]

def _safe_json_load(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    raw = raw.strip()
    # If model returns code fences or extra text, this will still fail;
    # keep it strict for now, we can add extraction if needed.
    try:
        return json.loads(raw)
    except Exception:
        return None

def _fallback_router(question: str):
    q = (question or "").lower()
    intents = []
    if any(x in q for x in ["portfolio", "case study", "resume", "pdf", "document"]):
        intents.append({"type": "DOC_REQUEST", "confidence": 0.75})
    if any(x in q for x in ["contact", "email", "phone", "linkedin"]):
        intents.append({"type": "CONTACT_LOOKUP", "confidence": 0.7})
    if any(x in q for x in ["refund", "return", "shipping", "warranty", "policy"]):
        intents.append({"type": "SUPPORT_FAQ", "confidence": 0.7})
    if any(x in q for x in ["buy", "price", "products", "collection"]):
        intents.append({"type": "PRODUCT_DISCOVERY", "confidence": 0.65})
    if not intents:
        intents.append({"type": "UNKNOWN", "confidence": 0.4})
    return intents[:2]


def detect_intents(question: str, max_intents: int = 2) -> List[Dict[str, Any]]:
    q = (question or "").strip()
    if not q:
        return _minimal_fallback(q, max_intents)

    client = get_openai_client()

    instructions = (
        "You are an intent router for a website chatbot.\n"
        "Return STRICT JSON only. No markdown. No commentary.\n"
        f"Allowed intent types: {', '.join(ALLOWED_INTENTS)}.\n"
        "Pick at most 2 intents.\n"
        "Each intent must include: type, confidence (0-1), query (short), requires_gating (bool).\n"
        "Set requires_gating=true for DOC_REQUEST or LEAD_GEN.\n"
        "If unclear, return UNKNOWN and set needs_clarification=true and provide clarifying_question.\n"
    )

    schema_hint = {
        "intents": [
            {"type": "SUPPORT_FAQ", "confidence": 0.0, "query": "", "requires_gating": False}
        ],
        "needs_clarification": False,
        "clarifying_question": "",
    }

    try:
        resp = client.responses.create(
            model=os.getenv("OPENAI_ROUTER_MODEL", "gpt-5-nano"),
            instructions=instructions,
            input=f"USER QUESTION:\n{q}\n\nOUTPUT MUST MATCH THIS JSON SHAPE:\n{json.dumps(schema_hint)}",
            text={"format": {"type": "text"}},
        )

        raw = (getattr(resp, "output_text", "") or "").strip()
        data = _safe_json_load(raw)
        if not data:
            return _minimal_fallback(q, max_intents)

        intents_in = data.get("intents") or []
        needs_clarification = bool(data.get("needs_clarification"))
        clarifying_question = (data.get("clarifying_question") or "").strip()

        cleaned = []
        seen = set()
        for it in intents_in:
            t = (it.get("type") or "").strip()
            if t not in ALLOWED_INTENTS or t in seen:
                continue
            seen.add(t)

            try:
                conf = float(it.get("confidence") or 0.0)
            except Exception:
                conf = 0.0

            cleaned.append({
                "type": t,
                "confidence": max(0.0, min(1.0, conf)),
                "query": (it.get("query") or q)[:140],
                "roles": INTENT_TO_ROLES.get(t, []),
                "requires_gating": bool(it.get("requires_gating")) or (t in GATED_INTENTS),
                "needs_clarification": needs_clarification,
                "clarifying_question": clarifying_question,
            })

        if not cleaned:
            return _minimal_fallback(q, max_intents)

        # drop UNKNOWN if we have something else
        if len(cleaned) > 1:
            cleaned = [x for x in cleaned if x["type"] != "UNKNOWN"]

        cleaned = sorted(cleaned, key=lambda x: x["confidence"], reverse=True)[:max_intents]
        return cleaned

    except Exception:
        return _minimal_fallback(q, max_intents)
