# agents/views_chat.py
import json
import uuid
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from agents.models import Agent, Conversation, Message
from agents.services.chat_runtime import chat_answer


def _safe_json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None


def _intent_types(intents):
    return [i.get("type") for i in (intents or []) if i.get("type")]


def _build_used_from_evidence(evidence):
    """
    Convert evidence objects into a compact 'used' list that your UI debug panel
    can show (type + label). This also avoids [object Object] issues.
    """
    used = []
    for e in (evidence or [])[:8]:
        kind = e.get("kind") or "item"
        meta = e.get("meta") or {}
        label = meta.get("source_name") or e.get("title") or e.get("url") or "—"
        used.append({"type": kind, "label": str(label)[:140]})
    return used


@login_required
@require_POST
def agent_chat_api(request, agent_id: int):
    agent = get_object_or_404(Agent, pk=agent_id, user=request.user)

    payload = _safe_json(request)
    if payload is None:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    question = (payload.get("message") or payload.get("text") or "").strip()
    session_id = (payload.get("session_id") or payload.get("sessionId") or "").strip()[:80]

    lead = payload.get("lead") or {}
    lead_name = (lead.get("name") or "").strip()
    lead_email = (lead.get("email") or "").strip()

    if not question:
        return JsonResponse({"ok": False, "error": "message is required"}, status=400)

    if not session_id:
        session_id = str(uuid.uuid4())

    convo, _ = Conversation.objects.get_or_create(agent=agent, session_id=session_id)

    # store user message
    Message.objects.create(
        conversation=convo,
        role="user",
        content=question,
        meta={"lead": {"name": lead_name, "email": lead_email}},
    )

    try:
        result = chat_answer(
            agent=agent,
            user_message=question,
            lead={"name": lead_name, "email": lead_email},
            max_intents=2,
        )

        # Normalize debug so the UI shows readable strings, not [object Object]
        dbg = result.get("debug") or {}
        intents_full = dbg.get("intents") or []
        evidence = dbg.get("evidence") or []
        actions = result.get("actions") or []

        debug_out = {
            # UI-friendly
            "intents": _intent_types(intents_full),     # list[str]
            "used": _build_used_from_evidence(evidence),
            "actions": actions,

            # keep rich debug for deeper inspection if needed
            "intents_full": intents_full,
            "roles": dbg.get("roles") or [],
            "evidence": evidence,
            "gated": bool(dbg.get("gated")),
        }

        resp = {
            "ok": True,
            "session_id": session_id,
            "answer": (result.get("answer") or "").strip(),
            "messages": result.get("messages") or [{"type": "text", "text": (result.get("answer") or "").strip()}],
            "cards": result.get("cards") or [],
            "actions": actions,
            "debug": debug_out,
        }

        # store assistant message (store plain answer; keep debug in meta)
        Message.objects.create(
            conversation=convo,
            role="assistant",
            content=resp["answer"][:8000],
            meta={"debug": debug_out},
        )

        return JsonResponse(resp)

    except Exception as e:
        # return a compact error without breaking the UI
        err = str(e)[:300]
        Message.objects.create(
            conversation=convo,
            role="assistant",
            content=f"ERROR: {err}",
            meta={"error": err},
        )
        return JsonResponse({"ok": False, "error": err}, status=500)
