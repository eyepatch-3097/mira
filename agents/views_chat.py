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

@login_required
@require_POST
def agent_chat_api(request, agent_id: int):
    agent = get_object_or_404(Agent, pk=agent_id, user=request.user)

    payload = _safe_json(request)
    if payload is None:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    session_id = (payload.get("session_id") or payload.get("sessionId") or "").strip()[:80]
    message = (payload.get("message") or payload.get("text") or "").strip()

    if not session_id:
        session_id = str(uuid.uuid4())

    convo, _ = Conversation.objects.get_or_create(agent=agent, session_id=session_id)
    state = convo.state or {}

    # 1) Persist lead if provided
    incoming_lead = payload.get("lead") or {}
    lead_name = (incoming_lead.get("name") or "").strip()
    lead_email = (incoming_lead.get("email") or "").strip()

    if lead_name and lead_email:
        state["lead"] = {"name": lead_name, "email": lead_email}
        convo.state = state
        convo.save(update_fields=["state", "updated_at"])

    stored_lead = (convo.state or {}).get("lead") or {}

    # 2) Continue after lead submit
    if message == "__continue__":
        pending = (state.get("pending_message") or "").strip()
        if pending:
            message = pending
        else:
            return JsonResponse({"ok": False, "error": "Nothing pending to continue."}, status=400)

    if not message:
        return JsonResponse({"ok": False, "error": "message is required"}, status=400)

    # Log user msg
    Message.objects.create(
        conversation=convo,
        role="user",
        content=message,
        meta={"lead": stored_lead},
    )

    # 3) Run brain
    try:
        result = chat_answer(agent=agent, user_message=message, lead=stored_lead)

        # 4) If lead form is required but lead not present -> store pending message
        actions = result.get("actions") or []
        needs_lead = any(a.get("type") == "lead_form" for a in actions)

        if needs_lead and not stored_lead:
            state["pending_message"] = message
            convo.state = state
            convo.save(update_fields=["state", "updated_at"])
        else:
            # clear pending if resolved
            state.pop("pending_message", None)
            convo.state = state
            convo.save(update_fields=["state", "updated_at"])

        resp = {"ok": True, "session_id": session_id, **result}

        Message.objects.create(
            conversation=convo,
            role="assistant",
            content=(resp.get("answer") or "")[:4000],
            meta={"debug": resp.get("debug") or {}},
        )

        return JsonResponse(resp)

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)[:300]}, status=500)
