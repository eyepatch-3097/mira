from django.conf import settings
from django.db import models
from django.contrib.auth.models import User

class DataSource(models.Model):
    TYPE_CHOICES = [
        ("website", "Website"),
        ("document", "Document"),
        ("sheet", "Sheet"),
        ("custom", "Custom"),
    ]
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("pending", "Pending"),
        ("running", "Running"),
        ("done", "Done"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="data_sources")
    name = models.CharField(max_length=120)
    source_type = models.CharField(max_length=20, choices=TYPE_CHOICES)

    domain_url = models.URLField(blank=True)  # only for website
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    error_message = models.CharField(max_length=300, blank=True)

    total_pages = models.IntegerField(default=0)
    selected_pages = models.IntegerField(default=0)
    processed_pages = models.IntegerField(default=0)
    source_context = models.TextField(blank=True, default="")
    summary = models.TextField(blank=True, default="")

    file = models.FileField(upload_to="sources/uploads/%Y/%m/", blank=True, null=True)
    original_filename = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.source_type})"


class DataSourcePage(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("done", "Done"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    ]
    CATEGORY_CHOICES = [
        ("blog", "Blog"),
        ("product", "Product"),
        ("info", "Info"),
    ]

    source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="pages")
    url = models.URLField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="info")

    selected = models.BooleanField(default=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    summary = models.TextField(blank=True)
    error = models.CharField(max_length=300, blank=True)
    preview = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("source", "url")]
        indexes = [
            models.Index(fields=["source", "category", "selected"]),
            models.Index(fields=["source", "status"]),
        ]

    def __str__(self):
        return self.url
