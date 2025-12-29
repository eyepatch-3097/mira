# agents/views_lead.py
import json
from django.http import JsonResponse, FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from agents.models import Agent, Conversation, DocumentAccessToken
from agents.services.gating import create_lead, mark_lead_captured, mint_doc_token
from sources.models import DataSource


@login_required
@require_POST
def agent_lead_submit(request, agent_id: int):
    agent = get_object_or_404(Agent, pk=agent_id, user=request.user)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    session_id = (payload.get("session_id") or "").strip()[:80]
    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip()
    reason = (payload.get("reason") or "").strip()  # doc_gate / lead_gen
    question = (payload.get("question") or "").strip()

    if not (session_id and name and email and reason):
        return JsonResponse({"ok": False, "error": "Missing fields"}, status=400)

    convo = get_object_or_404(Conversation, agent=agent, session_id=session_id)

    lead = create_lead(agent, convo, name, email, source=reason, question=question)
    mark_lead_captured(convo, reason, lead.id)

    # If doc gate, mint token for FIRST document_referral source (simple v1)
    doc_url = ""
    if reason == "doc_gate":
        # pick a document data source linked to agent (document_referral role)
        # you can later choose based on router evidence
        from agents.models import AgentDataSource
        link = (
            AgentDataSource.objects.filter(agent=agent, role="document_referral")
            .select_related("source")
            .first()
        )
        if link and link.source and link.source.file:
            tok = mint_doc_token(lead, link.source)
            doc_url = f"/agents/doc/{tok.token}/"

    return JsonResponse({"ok": True, "doc_url": doc_url})


def doc_download_by_token(request, token: str):
    tok = get_object_or_404(DocumentAccessToken, token=token)

    if tok.expires_at < timezone.now():
        raise Http404("Token expired")

    ds = tok.data_source
    if not ds.file:
        raise Http404("File missing")

    # optional: set used_at
    if not tok.used_at:
        tok.used_at = timezone.now()
        tok.save(update_fields=["used_at"])

    return FileResponse(ds.file.open("rb"), as_attachment=True, filename=ds.original_filename or "document")
