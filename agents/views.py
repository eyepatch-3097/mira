# agents/views.py
import json
import uuid
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from .forms import AgentCreateForm
from .models import Agent, AgentDataSource, Conversation, Message
from sources.models import DataSource
from agents.services.indexer import rebuild_agent_index
from agents.services.chat_runtime import chat_answer
from collections import defaultdict

ROLE_ALLOWED_TYPES = {
    "website_guidance": {"website", "custom"},
    "contact_data": {"sheet", "custom", "website"},
    "support_faq": {"custom", "website", "document"},
    "document_referral": {"document"},
}

ROLE_META = [
    ("website_guidance", "Website Guidance", "Helps users navigate to the right page."),
    ("contact_data", "Contact Data", "Used to answer contact/team/CRM-style questions."),
    ("support_faq", "Support FAQ", "Used for policies, FAQs, troubleshooting and support."),
    ("document_referral", "Document Referral", "Used to recommend documents (can be gated later)."),
]

@login_required
def agent_detail(request, agent_id: int):
    agent = get_object_or_404(Agent, pk=agent_id, user=request.user)

    # Fetch all attached sources (and their tags) in one go
    links = (
        AgentDataSource.objects
        .filter(agent=agent)
        .select_related("source")
        .prefetch_related("source__tags")
        .order_by("role", "-created_at")
    )

    role_to_sources = defaultdict(list)
    for link in links:
        role_to_sources[link.role].append(link.source)

    # Build role sections for UI
    role_blocks = []
    for role, title, desc in ROLE_META:
        role_blocks.append({
            "role": role,
            "title": title,
            "desc": desc,
            "allowed_types": sorted(list(ROLE_ALLOWED_TYPES.get(role, []))),
            "sources": role_to_sources.get(role, []),
        })

    return render(request, "agents/agent_detail.html", {
        "agent": agent,
        "role_blocks": role_blocks,
        "total_attached": links.count(),
    })

@login_required
def agent_list(request):
    agents = Agent.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "agents/agent_list.html", {"agents": agents})

@login_required
def agent_new(request):
    if request.method == "POST":
        form = AgentCreateForm(request.POST, request.FILES)
        if form.is_valid():
            agent = form.save(commit=False)
            agent.user = request.user
            agent.save()
            return redirect("agent_sources", agent_id=agent.id)
    else:
        form = AgentCreateForm()

    return render(request, "agents/agent_new.html", {"form": form})

@login_required
def agent_edit(request, agent_id: int):
    agent = get_object_or_404(Agent, pk=agent_id, user=request.user)

    next_url = request.GET.get("next") or ""
    if next_url and not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = ""

    if request.method == "POST":
        form = AgentCreateForm(request.POST, request.FILES, instance=agent)
        if form.is_valid():
            form.save()
            return redirect(next_url or reverse("agent_test", args=[agent.id]))
    else:
        form = AgentCreateForm(instance=agent)

    return render(request, "agents/agent_edit.html", {"form": form, "agent": agent})

@login_required
def agent_sources(request, agent_id: int):
    agent = get_object_or_404(Agent, pk=agent_id, user=request.user)

    # Fetch current selections
    existing = AgentDataSource.objects.filter(agent=agent).values("role", "source_id")
    selected_map = {k: set() for k in ROLE_ALLOWED_TYPES.keys()}
    for row in existing:
        selected_map[row["role"]].add(row["source_id"])

    # Eligible sources per role
    eligible_map = {}
    for role, allowed in ROLE_ALLOWED_TYPES.items():
        eligible_map[role] = (
            DataSource.objects.filter(user=request.user, source_type__in=list(allowed))
            .order_by("-created_at")
            .prefetch_related("tags")
        )

    if request.method == "POST":
        with transaction.atomic():
            # Replace selections role-by-role
            for role, allowed_types in ROLE_ALLOWED_TYPES.items():
                posted_ids = request.POST.getlist(f"{role}_ids")
                ids = [int(x) for x in posted_ids if str(x).isdigit()]

                # validate ownership + allowed type
                qs = DataSource.objects.filter(
                    user=request.user,
                    id__in=ids,
                    source_type__in=list(allowed_types),
                )
                valid_sources = list(qs.values_list("id", flat=True))

                # wipe old role links, then add new ones
                AgentDataSource.objects.filter(agent=agent, role=role).delete()
                AgentDataSource.objects.bulk_create(
                    [
                        AgentDataSource(agent=agent, source_id=sid, role=role)
                        for sid in valid_sources
                    ],
                    ignore_conflicts=True,
                )
            
        transaction.on_commit(lambda: rebuild_agent_index(agent))

        messages.success(request, "Saved agent data sources. Opening test chat...")
        return redirect("agent_test", agent_id=agent.id)

    # Build UI cards data
    role_blocks = []
    for role, title, desc in ROLE_META:
        role_blocks.append({
            "role": role,
            "title": title,
            "desc": desc,
            "sources": eligible_map[role],
            "selected_ids": selected_map.get(role, set()),
            "allowed_types": sorted(list(ROLE_ALLOWED_TYPES[role])),
        })

    return render(request, "agents/agent_sources.html", {
        "agent": agent,
        "role_blocks": role_blocks,
    })

@login_required
def agent_test(request, agent_id: int):
    agent = get_object_or_404(Agent, pk=agent_id, user=request.user)
    return render(request, "agents/agent_test.html", {"agent": agent})

