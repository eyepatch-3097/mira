from __future__ import annotations
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse
from .forms import SignupForm, ProfileUpdateForm
from landing.tracking import log_pageview  # we’ll create this in section D
from agents.models import Agent, Conversation, Message

from datetime import datetime, timedelta, time
from collections import Counter
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.apps import apps

class MiraLoginView(LoginView):
    template_name = "accounts/login.html"

    def dispatch(self, request, *args, **kwargs):
        log_pageview(request, path="/login/")
        return super().dispatch(request, *args, **kwargs)

class MiraLogoutView(LogoutView):
    next_page = "/"

def signup(request):
    log_pageview(request, path="/signup/")

    # Store UTMs in session for later onboarding attribution (optional but useful)
    utm = {k: request.GET.get(k) for k in ["utm_source","utm_medium","utm_campaign","utm_content","utm_term"] if request.GET.get(k)}
    if utm:
        request.session["utm"] = utm

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("/dashboard")  # later: redirect to onboarding
    else:
        form = SignupForm()

    return render(request, "accounts/signup.html", {"form": form})


@login_required
def dashboard(request):
    agents = Agent.objects.filter(user=request.user).order_by("-created_at")
    log_pageview(request, path="/dashboard/")
    return render(request, "accounts/dashboard.html", {"agents": agents})

@login_required
def edit_profile(request):
    log_pageview(request, path="/profile/edit/")

    profile = request.user.profile

    if request.method == "POST":
        form = ProfileUpdateForm(request.POST, request.FILES, instance=profile, user=request.user)
        if form.is_valid():
            form.save()
            return redirect("/dashboard/")
    else:
        form = ProfileUpdateForm(instance=profile, user=request.user)

    return render(request, "accounts/edit_profile.html", {"form": form})

@login_required
def data_sources(request):
    log_pageview(request, path="/data-sources/")
    selected = request.GET.get("type", "")
    return render(request, "accounts/data_sources.html", {"selected": selected})

