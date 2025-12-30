# agents/services/chat_runtime.py
import os
import json
from typing import Dict, Any, List

from agents.services.openai_client import get_openai_client
from agents.services.router import detect_intents
from agents.services.retrieval import retrieve

DOC_INTENT = "DOC_REQUEST"
LEAD_INTENT = "LEAD_GEN"
CONTACT_INTENT = "CONTACT_LOOKUP"

CARD_INTENTS = {"NAVIGATE_PAGE", "PRODUCT_DISCOVERY", "SUPPORT_FAQ"}


def _lead_present(lead: Dict[str, str]) -> bool:
    if not lead:
        return False
    email = (lead.get("email") or "").strip()
    name = (lead.get("name") or "").strip()
    return bool(email) and bool(name)


def _safe_json_loads(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _build_evidence_for_prompt(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # keep it compact
    out = []
    for e in (evidence or [])[:10]:
        out.append({
            "kind": e.get("kind"),
            "role": e.get("role"),
            "title": (e.get("title") or "")[:140],
            "url": e.get("url") or "",
            "tags": (e.get("tags") or [])[:12],
            "snippet": (e.get("text") or "")[:650],
            "meta": e.get("meta") or {},
        })
    return out


def _cards_from_evidence(intents: List[Dict[str, Any]], evidence: List[Dict[str, Any]], max_cards: int = 6) -> List[Dict[str, Any]]:
    intent_types = {i.get("type") for i in (intents or [])}
    if not (intent_types & CARD_INTENTS):
        return []

    cards: List[Dict[str, Any]] = []
    seen = set()

    for e in (evidence or []):
        if e.get("kind") != "page":
            continue
        url = (e.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)

        meta = e.get("meta") or {}
        title = meta.get("source_name") or e.get("title") or "Relevant page"
        subtitle = ((e.get("text") or "").strip())[:160]

        cards.append({
            "title": str(title)[:140],
            "url": url,
            "subtitle": subtitle,
            "thumbnail": "",
        })

        if len(cards) >= max_cards:
            break

    return cards


def chat_answer(
    *,
    agent,
    user_message: str,
    lead: Dict[str, str] | None = None,
    max_intents: int = 2,
) -> Dict[str, Any]:
    """
    Core rules for your desired workflow:

    A) CONNECT / REACH OUT:
       - If intent is LEAD_GEN or CONTACT_LOOKUP:
         - If lead missing -> show ONLY a simple message + lead_form action (NO retrieval, NO cards, NO LLM).
         - If lead present -> show ONLY a thank you confirmation (NO retrieval, NO cards, NO LLM).

    B) NORMAL Q&A:
       - Use retrieval + deterministic cards.
       - LLM writes the answer in brand voice using evidence.

    C) OFF-TOPIC:
       - If no evidence found, respond that we can only help with site/services/docs.
    """
    lead = lead or {}
    lead_ok = _lead_present(lead)

    # 1) Intent routing (AI)
    intents = detect_intents(user_message, max_intents=max_intents)
    intent_types = {i.get("type") for i in (intents or [])}

    has_doc = DOC_INTENT in intent_types
    has_lead = LEAD_INTENT in intent_types
    has_contact = CONTACT_INTENT in intent_types

    # --- HARD RULE: CONNECT FLOW IS UI-FIRST (no retrieval, no cards, no LLM) ---
    if has_lead or has_contact:
        if not lead_ok:
            return {
                "answer": "Sure — please share your name and email below and we’ll connect you with the right person.",
                "messages": [{"type": "text", "text": "Sure — please share your name and email below and we’ll connect you with the right person."}],
                "cards": [],
                "actions": [{
                    "type": "lead_form",
                    "reason": "lead_gen" if has_lead else "contact_lookup",
                    "fields": ["name", "email"],
                    "cta": "Continue",
                }],
                "debug": {
                    "intents": intents,
                    "roles": [],
                    "evidence": [],
                    "gated": True,
                }
            }

        # lead already captured
        name = (lead.get("name") or "").strip() or "there"
        email = (lead.get("email") or "").strip()
        confirm = f"Thanks, {name} — we’ve received your details"
        if email:
            confirm += f" ({email})"
        confirm += ". Someone from our team will reach out shortly."

        return {
            "answer": confirm,
            "messages": [{"type": "text", "text": confirm}],
            "cards": [],
            "actions": [],
            "debug": {
                "intents": intents,
                "roles": [],
                "evidence": [],
                "gated": False,
            }
        }

    # 2) Retrieval roles
    roles = sorted({r for it in intents for r in (it.get("roles") or [])})

    # 3) Retrieval
    evidence: List[Dict[str, Any]] = []
    if roles:
        for it in intents:
            r = it.get("roles") or []
            if not r:
                continue
            q = (it.get("query") or user_message).strip()
            evidence.extend(retrieve(agent=agent, roles=r, query=q, limit=8))

    # de-dupe
    seen = set()
    uniq = []
    for e in (evidence or []):
        key = (e.get("kind"), e.get("page_id") or 0, e.get("source_id") or 0, (e.get("url") or "").strip())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    evidence = uniq[:12]

    # 4) DOC workflow (only gate if we actually found a relevant doc/source)
    # If doc requested but nothing exists -> refuse gracefully
    if has_doc:
        if not evidence:
            msg = "I don’t have that document/info in my configured sources. I can help with our services/pages, support FAQs, or specific documents that are available."
            return {
                "answer": msg,
                "messages": [{"type": "text", "text": msg}],
                "cards": [],
                "actions": [],
                "debug": {"intents": intents, "roles": roles, "evidence": [], "gated": False}
            }

        if not lead_ok:
            msg = "I can share that — please enter your name and email below and I’ll provide it right after."
            return {
                "answer": msg,
                "messages": [{"type": "text", "text": msg}],
                "cards": [],
                "actions": [{
                    "type": "lead_form",
                    "reason": "doc_gate",
                    "fields": ["name", "email"],
                    "cta": "Continue",
                }],
                "debug": {"intents": intents, "roles": roles, "evidence": evidence[:6], "gated": True}
            }

        # lead ok + doc exists -> continue to normal answering (LLM) but still DO NOT invent URLs
        # cards will be created deterministically below.

    # 5) Cards (deterministic)
    cards = _cards_from_evidence(intents, evidence, max_cards=6)

    # 6) Off-topic guard (no evidence + not greeting/smalltalk)
    if not evidence:
        msg = (
            "I’m sorry — I can only answer questions based on our configured website/pages and resources. "
            "Try asking about our services, case studies, support/policies, or specific pages you want to find."
        )
        return {
            "answer": msg,
            "messages": [{"type": "text", "text": msg}],
            "cards": [],
            "actions": [],
            "debug": {"intents": intents, "roles": roles, "evidence": [], "gated": False}
        }

    # 7) LLM answer composer (brand voice + evidence)
    client = get_openai_client()

    system = (
        "You are the website chatbot for the given brand.\n"
        "Write in first-person plural (we/our) as the brand.\n"
        "Be specific and helpful.\n\n"
        "You are given EVIDENCE items pulled from configured data sources.\n"
        "Answer using evidence; do NOT invent URLs.\n"
        "If suggested_pages exist, encourage the user to open them.\n\n"
        "Return STRICT json only in this format:\n"
        "{answer: string, messages: [{type:'text', text:string}]}\n"
    )

    payload = {
        "agent": {
            "name": getattr(agent, "name", ""),
            "description": getattr(agent, "description", ""),
        },
        "user_message": user_message,
        "intents": intents,
        "lead_present": lead_ok,
        "evidence": _build_evidence_for_prompt(evidence),
        "suggested_pages": cards,  # deterministic list
        "must_not_invent_urls": True,
    }

    resp = client.responses.create(
        model=os.getenv("OPENAI_CHAT_MODEL", "gpt-5-nano"),
        instructions=system,
        input="json request:\n" + json.dumps(payload),
        text={"format": {"type": "json_object"}},
    )

    raw = (getattr(resp, "output_text", "") or "").strip()
    data = _safe_json_loads(raw)

    answer = (data.get("answer") or "").strip() or "Got it — how can we help?"
    messages = data.get("messages") or [{"type": "text", "text": answer}]

    return {
        "answer": answer,
        "messages": messages,
        "cards": cards[:6],
        "actions": [],
        "debug": {
            "intents": intents,
            "roles": roles,
            "evidence": evidence[:6],
            "gated": False,
        }
    }
