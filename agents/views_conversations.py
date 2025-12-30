# agents/views_conversations.py
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from agents.models import Agent, Conversation, Message


@login_required
def conversations_list(request):
    """
    List all conversations across all agents owned by the logged-in user.
    Optional filters:
      - ?agent=<agent_id>
      - ?q=<search>
    """
    qs = (
        Conversation.objects
        .select_related("agent")
        .filter(agent__user=request.user)
        .order_by("-updated_at", "-id")
    )

    agent_id = (request.GET.get("agent") or "").strip()
    if agent_id.isdigit():
        qs = qs.filter(agent_id=int(agent_id))

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(session_id__icontains=q) |
            Q(agent__name__icontains=q)
        )

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    agents = Agent.objects.filter(user=request.user).order_by("name")

    return render(request, "agents/conversations_list.html", {
        "page_obj": page_obj,
        "agents": agents,
        "selected_agent": agent_id,
        "q": q,
    })


@login_required
def conversation_detail(request, convo_id: int):
    """
    Show a single conversation transcript (owner-only).
    """
    convo = get_object_or_404(
        Conversation.objects.select_related("agent"),
        pk=convo_id,
        agent__user=request.user,
    )

    messages = (
        Message.objects
        .filter(conversation=convo)
        .order_by("created_at", "id")
    )

    lead = (convo.state or {}).get("lead") or {}

    return render(request, "agents/conversation_detail.html", {
        "convo": convo,
        "messages": messages,
        "lead": lead,
    })
