# agents/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("new/", views.agent_new, name="agent_new"),
    path("<int:agent_id>/", views.agent_detail, name="agent_detail"),
]
