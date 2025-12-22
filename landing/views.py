from django.shortcuts import render
from .tracking import log_pageview

def home(request):
    log_pageview(request, path="/")
    return render(request, "landing/home.html")
