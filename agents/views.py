# agents/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .forms import AgentCreateForm

@login_required
def agent_new(request):
    if request.method == "POST":
        form = AgentCreateForm(request.POST, request.FILES)
        if form.is_valid():
            agent = form.save(commit=False)
            agent.user = request.user
            agent.save()
            return redirect("agent_detail", agent_id=agent.id)  # next page later
    else:
        form = AgentCreateForm()

    return render(request, "agents/agent_new.html", {"form": form})


@login_required
def agent_detail(request, agent_id: int):
    # placeholder for now (next steps: attach sources, preview chat, etc.)
    from .models import Agent
    agent = Agent.objects.get(pk=agent_id, user=request.user)
    return render(request, "agents/agent_detail.html", {"agent": agent})
