import uuid
from django.conf import settings
from django.db import models

class Profile(models.Model):
    INDUSTRY_CHOICES = [
        ("d2c", "D2C"),
        ("ecommerce", "E-commerce"),
        ("saas", "SaaS"),
        ("retail", "Retail"),
        ("services", "Services"),
        ("other", "Other"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True)

    company_name = models.CharField(max_length=120, blank=True)
    industry = models.CharField(max_length=32, choices=INDUSTRY_CHOICES, blank=True)
    custom_industry = models.CharField(max_length=120, blank=True)

    company_description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} • {self.public_id}"
