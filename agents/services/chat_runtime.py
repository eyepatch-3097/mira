# agents/services/chat_runtime.py
import os
import json
from typing import Dict, Any, List

from agents.services.openai_client import get_openai_client
from agents.services.router import detect_intents
from agents.services.retrieval import retrieve

DOC_INTENT = "DOC_REQUEST"
LEAD_INTENT = "LEAD_GEN"


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
    """
    Keep only what the model needs. Prevent huge payloads.
    """
    out = []
    for e in evidence[:10]:
        out.append({
            "kind": e.get("kind"),
            "role": e.get("role"),
            "title": (e.get("title") or "")[:140],
            "url": e.get("url") or "",
            "tags": (e.get("tags") or [])[:12],
            "snippet": (e.get("text") or "")[:600],
            "meta": e.get("meta") or {},
            "source_id": e.get("source_id"),
            "page_id": e.get("page_id"),
        })
    return out


def chat_answer(
    *,
    agent,
    user_message: str,
    lead: Dict[str, str] | None = None,
    max_intents: int = 2,
) -> Dict[str, Any]:
    """
    Returns a consistent structure:
    {
      answer: str,
      messages: [{type:'text', text:'...'}],
      cards: [{title,url,subtitle,thumbnail}],
      actions: [...],
      debug: {...}
    }
    """
    lead = lead or {}
    client = get_openai_client()

    # 1) Intent routing (LLM)
    intents = detect_intents(user_message, max_intents=max_intents)

    roles = sorted({r for it in intents for r in (it.get("roles") or [])})

    has_doc = any(i.get("type") == DOC_INTENT for i in intents)
    has_lead = any(i.get("type") == LEAD_INTENT for i in intents)

    gated = (has_doc or has_lead) and (not _lead_present(lead))

    # 2) Retrieval (scoped by roles)
    evidence = []
    if roles:
        # do per-intent retrieval to keep scope tight
        for it in intents:
            r = it.get("roles") or []
            if not r:
                continue
            q = (it.get("query") or user_message).strip()
            evidence.extend(retrieve(agent, r, q, limit=6))

    # de-dupe evidence
    seen = set()
    uniq = []
    for e in evidence:
        key = (e.get("kind"), e.get("page_id") or 0, e.get("source_id") or 0, e.get("url") or "")
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    evidence = uniq[:10]

    # 3) Gating actions (UI will render later)
    actions = []
    if gated:
        reason = "doc_gate" if has_doc else "lead_gen"
        actions.append({
            "type": "lead_form",
            "reason": reason,
            "fields": ["name", "email"],
            "cta": "Continue",
        })

    # 4) LLM composer (this is the missing “intelligence” layer)
    #    Output: STRICT JSON with answer/messages/cards
    system = (
        "You are a helpful website chatbot.\n"
        "Always be natural and conversational.\n"
        "You can greet users and handle smalltalk.\n"
        "\n"
        "You are given EVIDENCE items (pages/sources) chosen from the chatbot's configured data sources.\n"
        "Use evidence to answer accurately. If evidence is missing, ask 1 clarifying question.\n"
        "\n"
        "GATING RULE:\n"
        "- If gated=true, DO NOT reveal direct document links or gated resources.\n"
        "- Instead, politely ask for name+email and confirm you'll share after.\n"
        "\n"
        "Return STRICT JSON only in the required format."
    )

    payload = {
        "agent": {
            "name": getattr(agent, "name", ""),
            "description": getattr(agent, "description", ""),
            "greeting_message": getattr(agent, "greeting_message", "") or "Hi! How can I help?",
        },
        "user_message": user_message,
        "intents": intents,
        "roles": roles,
        "gated": gated,
        "lead_present": _lead_present(lead),
        "evidence": _build_evidence_for_prompt(evidence),
        "required_output_format": {
            "answer": "string (required, non-empty)",
            "messages": [{"type": "text", "text": "string"}],
            "cards": [{"title": "string", "url": "string", "subtitle": "string", "thumbnail": ""}],
            "actions": [{"type": "string", "reason": "string"}],
            "needs_clarification": False,
            "clarifying_question": "",
        }
    }

    resp = client.responses.create(
        model=os.getenv("OPENAI_CHAT_MODEL", "gpt-5-nano"),
        instructions=system,
        input="Respond in JSON only.\n\n" + json.dumps(payload),
        text={"format": {"type": "json_object"}},
    )

    raw = (getattr(resp, "output_text", "") or "").strip()
    data = _safe_json_loads(raw)

    answer = (data.get("answer") or "").strip()
    messages = data.get("messages") or []
    cards = data.get("cards") or []
    needs_clarification = bool(data.get("needs_clarification"))
    clarifying_question = (data.get("clarifying_question") or "").strip()

    # Hard safety: ensure answer is never empty
    if not answer:
        if needs_clarification and clarifying_question:
            answer = clarifying_question
        else:
            answer = "Got it. What would you like to know specifically?"

    # If model forgot to include gating actions, enforce
    if gated and not actions:
        actions = [{
            "type": "lead_form",
            "reason": "doc_gate" if has_doc else "lead_gen",
            "fields": ["name", "email"],
            "cta": "Continue",
        }]

    # Merge enforced actions
    # (Model can also propose actions; we keep ours as truth)
    model_actions = data.get("actions") or []
    merged_actions = actions or model_actions

    return {
        "answer": answer,
        "messages": messages if messages else [{"type": "text", "text": answer}],
        "cards": cards[:6],
        "actions": merged_actions,
        "debug": {
            "intents": intents,
            "roles": roles,
            "evidence": evidence[:6],
            "gated": gated,
        }
    }
