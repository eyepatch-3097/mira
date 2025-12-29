# agents/urls.py
from django.urls import path
from . import views
from agents.views_chat import agent_chat_api
from agents.views_lead import agent_lead_submit, doc_download_by_token

urlpatterns = [
    path("new/", views.agent_new, name="agent_new"),
    path("<int:agent_id>/", views.agent_detail, name="agent_detail"),
    path("", views.agent_list, name="agent_list"),
    path("<int:agent_id>/edit/", views.agent_edit, name="agent_edit"),
    path("agents/<int:agent_id>/sources/", views.agent_sources, name="agent_sources"),
    path("agents/<int:agent_id>/lead/", agent_lead_submit, name="agent_lead_submit"),
    path("agents/doc/<str:token>/", doc_download_by_token, name="doc_download_by_token"),
    path("agents/<int:agent_id>/test/", views.agent_test, name="agent_test"),
    path("agents/<int:agent_id>/chat/", agent_chat_api, name="agent_chat_api"),
]
