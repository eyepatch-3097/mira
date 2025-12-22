from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse
from .forms import SignupForm, ProfileUpdateForm
from landing.tracking import log_pageview  # we’ll create this in section D

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
    log_pageview(request, path="/dashboard/")
    return render(request, "accounts/dashboard.html")

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