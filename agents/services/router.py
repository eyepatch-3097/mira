# agents/services/router.py
import os
import json
from typing import Any, Dict, List, Optional

from agents.services.openai_client import get_openai_client

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
    "LEAD_GEN": ["website_guidance", "support_faq", "contact_data"],
    "SMALLTALK": [],
    "UNKNOWN": [],
}

# These should trigger your lead-form UX downstream
GATED_INTENTS = {"DOC_REQUEST", "LEAD_GEN", "CONTACT_LOOKUP"}


def _minimal_unknown(question: str) -> List[Dict[str, Any]]:
    q = (question or "").strip()
    return [{
        "type": "UNKNOWN",
        "confidence": 0.2,
        "query": (q[:140] if q else "unknown"),
        "roles": [],
        "requires_gating": False,
        "needs_clarification": True,
        "clarifying_question": "What would you like help with—services, navigating the site, support/policies, documents, or reaching the team?",
    }]


def _safe_json_loads(raw: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads((raw or "").strip())
    except Exception:
        return None


def _canonical_intent(val: Any) -> str:
    """
    Canonicalize model output to our enum.
    This is NOT keyword routing; it's just normalization of the label.
    """
    s = (val or "")
    if not isinstance(s, str):
        return ""
    s = s.strip().upper()
    # common variations the model might produce
    s = s.replace("-", "_").replace(" ", "_")
    return s


def detect_intents(question: str, max_intents: int = 2) -> List[Dict[str, Any]]:
    q = (question or "").strip()
    if not q:
        return _minimal_unknown(q)[:max_intents]

    client = get_openai_client()

    # JSON mode requirement: input must contain the word "json"
    instructions = (
        "You are an intent router for a website chatbot.\n"
        "Return STRICT json only (no markdown, no commentary).\n"
        f"Allowed intent types (MUST match EXACTLY): {', '.join(ALLOWED_INTENTS)}.\n"
        "Pick at most 2 intents.\n"
        "Each intent MUST include:\n"
        "- type: one of the allowed intent types EXACTLY\n"
        "- confidence: number from 0 to 1\n"
        "- query: a short retrieval query to find relevant pages\n"
        "- requires_gating: true for DOC_REQUEST / LEAD_GEN / CONTACT_LOOKUP, else false\n"
        "Also include:\n"
        "- needs_clarification: boolean\n"
        "- clarifying_question: string (empty if not needed)\n"
        "\n"
        "Routing rules:\n"
        "- Business/marketing problem statements (CAC, ROAS, conversions, retention, growth) => PRODUCT_DISCOVERY\n"
        "- User asks to reach out / book a call / demo / speak to someone => LEAD_GEN\n"
        "- User asks for email/phone/contact details => CONTACT_LOOKUP (may also add LEAD_GEN as 2nd intent)\n"
        "- User requests a portfolio/resume/pdf/document => DOC_REQUEST\n"
        "- Greeting => GREETING\n"
        "- If unclear => UNKNOWN + ask ONE clarifying question\n"
        "\n"
        "Output must be valid json."
    )

    schema = {
        "intents": [
            {"type": "PRODUCT_DISCOVERY", "confidence": 0.7, "query": "short query", "requires_gating": False}
        ],
        "needs_clarification": False,
        "clarifying_question": "",
    }

    # A few examples improve stability WITHOUT keyword routing in code.
    examples = [
        {"user": "Can I book a call with your team?", "intents": [{"type": "LEAD_GEN"}]},
        {"user": "What’s your email / phone number?", "intents": [{"type": "CONTACT_LOOKUP"}, {"type": "LEAD_GEN"}]},
        {"user": "My CAC is too high, what should I do?", "intents": [{"type": "PRODUCT_DISCOVERY"}]},
        {"user": "Hi", "intents": [{"type": "GREETING"}]},
        {"user": "Share your portfolio / resume", "intents": [{"type": "DOC_REQUEST"}]},
    ]

    try:
        resp = client.responses.create(
            model=os.getenv("OPENAI_ROUTER_MODEL", "gpt-5-nano"),
            instructions=instructions,
            input="json request:\n" + json.dumps({
                "question": q,
                "schema": schema,
                "examples": examples,
            }),
            text={"format": {"type": "json_object"}},
        )

        raw = (getattr(resp, "output_text", "") or "").strip()
        data = _safe_json_loads(raw)
        if not data:
            return _minimal_unknown(q)[:max_intents]

        intents_in = data.get("intents") or []
        needs_clarification = bool(data.get("needs_clarification"))
        clarifying_question = (data.get("clarifying_question") or "").strip()

        cleaned: List[Dict[str, Any]] = []
        seen = set()

        for it in intents_in:
            t = _canonical_intent(it.get("type"))
            if not t or t not in ALLOWED_INTENTS or t in seen:
                continue
            seen.add(t)

            try:
                conf = float(it.get("confidence") or 0.0)
            except Exception:
                conf = 0.0
            conf = max(0.0, min(1.0, conf))

            cleaned.append({
                "type": t,
                "confidence": conf,
                "query": (it.get("query") or q)[:140],
                "roles": INTENT_TO_ROLES.get(t, []),
                "requires_gating": bool(it.get("requires_gating")) or (t in GATED_INTENTS),
                "needs_clarification": needs_clarification,
                "clarifying_question": clarifying_question,
            })

        if not cleaned:
            return _minimal_unknown(q)[:max_intents]

        # drop UNKNOWN if something else exists
        if len(cleaned) > 1:
            cleaned = [x for x in cleaned if x["type"] != "UNKNOWN"]

        cleaned = sorted(cleaned, key=lambda x: x["confidence"], reverse=True)[:max_intents]
        return cleaned

    except Exception:
        # No keyword routing; only safe UNKNOWN fallback
        return _minimal_unknown(q)[:max_intents]
