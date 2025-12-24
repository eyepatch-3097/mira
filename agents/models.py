# agents/models.py
import uuid
from django.conf import settings
from django.db import models

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