# agents/models.py
import uuid
import secrets
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from sources.models import DataSource, DataSourcePage

class Agent(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agents"
    )

    # public id useful later for embed scripts
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    greeting_message = models.CharField(max_length=280, blank=True, default="Hi! How can I help you?")

    # icon for UI (requires Pillow)
    icon = models.ImageField(upload_to="agents/icons/%Y/%m/", blank=True, null=True)

    # UI colors (hex)
    title_bar_color = models.CharField(max_length=16, default="#0F172A")   # slate-900-ish
    window_bg_color = models.CharField(max_length=16, default="#020617")   # slate-950-ish
    bot_bubble_color = models.CharField(max_length=16, default="#0EA5A4")  # teal-500-ish
    user_bubble_color = models.CharField(max_length=16, default="#334155") # slate-700-ish
    text_color = models.CharField(max_length=16, default="#E2E8F0")        # slate-200-ish

    is_active = models.BooleanField(default=False)  # later: only active agents can be embedded

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

class AgentDataSource(models.Model):
    ROLE_CHOICES = [
        ("website_guidance", "Website Guidance"),
        ("contact_data", "Contact Data"),
        ("support_faq", "Support FAQ"),
        ("document_referral", "Document Referral"),
    ]

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="agent_links")
    role = models.CharField(max_length=30, choices=ROLE_CHOICES)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("agent", "source", "role")
        indexes = [
            models.Index(fields=["agent", "role"]),
            models.Index(fields=["source", "role"]),
        ]

    def __str__(self):
        return f"{self.agent_id} -> {self.source_id} ({self.role})"

class Conversation(models.Model):
    agent = models.ForeignKey("Agent", on_delete=models.CASCADE, related_name="conversations")
    session_id = models.CharField(max_length=80, db_index=True)
    state = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["agent", "session_id"], name="uniq_convo_agent_session"),
        ]
        indexes = [models.Index(fields=["agent", "session_id"])]


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20)  # user/assistant/system
    content = models.TextField(blank=True, default="")
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class LeadCapture(models.Model):
    agent = models.ForeignKey("Agent", on_delete=models.CASCADE, related_name="leads")
    conversation = models.ForeignKey(Conversation, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=120)
    email = models.EmailField()
    source = models.CharField(max_length=40)  # lead_gen | doc_gate
    question = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class DocumentAccessToken(models.Model):
    lead = models.ForeignKey(LeadCapture, on_delete=models.CASCADE, related_name="doc_tokens")
    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="doc_tokens")
    token = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def mint(cls, lead: LeadCapture, data_source: DataSource, hours_valid: int = 72):
        return cls.objects.create(
            lead=lead,
            data_source=data_source,
            token=secrets.token_urlsafe(32),
            expires_at=timezone.now() + timedelta(hours=hours_valid),
        )


class AgentIndexItem(models.Model):
    """
    Denormalized “knowledge base” rows for an Agent.
    - Website: 1 row per DataSourcePage
    - Document/Sheet/Custom: 1 row per DataSource
    """
    KIND_CHOICES = [("page", "Page"), ("source", "Source")]

    agent = models.ForeignKey("Agent", on_delete=models.CASCADE, related_name="index_items")
    role = models.CharField(max_length=40)  # website_guidance/contact_data/support_faq/document_referral
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)

    source = models.ForeignKey(DataSource, null=True, blank=True, on_delete=models.CASCADE)
    page = models.ForeignKey(DataSourcePage, null=True, blank=True, on_delete=models.CASCADE)

    title = models.CharField(max_length=200, blank=True, default="")
    url = models.CharField(max_length=600, blank=True, default="")
    text = models.TextField(blank=True, default="")          # summary + useful metadata
    tags_text = models.CharField(blank=True, default="")  # "returns,refund,policy"
    meta = models.JSONField(default=dict, blank=True)        # category, headers, preview, etc.

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["agent", "role", "page"],
                condition=Q(kind="page"),
                name="uniq_agent_role_page_item",
            ),
            models.UniqueConstraint(
                fields=["agent", "role", "source"],
                condition=Q(kind="source"),
                name="uniq_agent_role_source_item",
            ),
        ]
        indexes = [
            models.Index(fields=["agent", "role", "kind"]),
            models.Index(fields=["agent", "role"]),
            models.Index(fields=["source"]),
            models.Index(fields=["page"]),
        ]