# agents/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from .forms import AgentCreateForm
from .models import Agent


@login_required
def agent_detail(request, agent_id: int):
    # placeholder for now (next steps: attach sources, preview chat, etc.)
    from .models import Agent
    agent = Agent.objects.get(pk=agent_id, user=request.user)
    return render(request, "agents/agent_detail.html", {"agent": agent})

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
            return redirect("agent_list")
    else:
        form = AgentCreateForm()

    return render(request, "agents/agent_new.html", {"form": form})

@login_required
def agent_edit(request, agent_id: int):
    agent = get_object_or_404(Agent, pk=agent_id, user=request.user)

    if request.method == "POST":
        form = AgentCreateForm(request.POST, request.FILES, instance=agent)
        if form.is_valid():
            form.save()
            return redirect("agent_list")
    else:
        form = AgentCreateForm(instance=agent)

    return render(request, "agents/agent_edit.html", {"form": form, "agent": agent})

