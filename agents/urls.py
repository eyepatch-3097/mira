# agents/urls.py
from django.urls import path
from . import views
from agents.views_chat import agent_chat_api
from agents.views_lead import agent_lead_submit, doc_download_by_token
from agents.views_deploy import agent_deploy, agent_activate, agent_deactivate
from agents.views_embed import agent_embed_js, agent_embed_config, agent_embed_chat
from agents.views_conversations import conversations_list, conversation_detail


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
    path("agents/<int:agent_id>/deploy/", agent_deploy, name="agent_deploy"),
    path("agents/<int:agent_id>/activate/", agent_activate, name="agent_activate"),
    path("agents/<int:agent_id>/deactivate/", agent_deactivate, name="agent_deactivate"),
    path("embed/<uuid:public_id>.js", agent_embed_js, name="agent_embed_js"),
    path("embed/<uuid:public_id>/config/", agent_embed_config, name="agent_embed_config"),
    path("embed/<uuid:public_id>/chat/", agent_embed_chat, name="agent_embed_chat"),
    path("conversations/", conversations_list, name="conversations_list"),
    path("conversations/<int:convo_id>/", conversation_detail, name="conversation_detail"),
]
