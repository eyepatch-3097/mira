# agents/views_deploy.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from agents.models import Agent


@login_required
def agent_deploy(request, agent_id: int):
    agent = get_object_or_404(Agent, pk=agent_id, user=request.user)

    # absolute script url (works in local + prod)
    script_path = reverse("agent_embed_js", kwargs={"public_id": agent.public_id})
    script_src = request.build_absolute_uri(script_path)

    return render(request, "agents/agent_deploy.html", {
        "agent": agent,
        "script_src": script_src,
    })


@login_required
@require_POST
def agent_activate(request, agent_id: int):
    agent = get_object_or_404(Agent, pk=agent_id, user=request.user)
    if not agent.is_active:
        agent.is_active = True
        agent.save(update_fields=["is_active", "updated_at"])
    return redirect("agent_deploy", agent_id=agent.id)


@login_required
@require_POST
def agent_deactivate(request, agent_id: int):
    agent = get_object_or_404(Agent, pk=agent_id, user=request.user)
    if agent.is_active:
        agent.is_active = False
        agent.save(update_fields=["is_active", "updated_at"])
    return redirect("agent_deploy", agent_id=agent.id)
