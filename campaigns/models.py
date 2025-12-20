from django.db import models
from django.utils.text import slugify
from urllib.parse import urlencode, urljoin

class Campaign(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    details = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def _unique_slug(self):
        base = slugify(self.name)[:120] or "campaign"
        slug = base
        i = 2
        while Campaign.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{i}"
            i += 1
        return slug

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class CampaignLink(models.Model):
    CHANNEL_EMAIL = "email"
    CHANNEL_WHATSAPP = "whatsapp"
    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_WHATSAPP, "WhatsApp"),
    ]

    campaign = models.ForeignKey(Campaign, related_name="links", on_delete=models.CASCADE)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)

    landing_path = models.CharField(max_length=200, default="/")

    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=140, blank=True)
    utm_content = models.CharField(max_length=140, blank=True)
    utm_term = models.CharField(max_length=140, blank=True)

    total_sent = models.PositiveIntegerField(default=0)
    total_replies = models.PositiveIntegerField(default=0)

    # “visits” tracking:
    local_pageviews = models.PositiveIntegerField(default=0, editable=False)   # auto from Django
    posthog_visits = models.PositiveIntegerField(default=0)                    # manual for now

    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # sensible defaults
        if not self.utm_source:
            self.utm_source = "mira"
        if not self.utm_medium:
            self.utm_medium = self.channel
        if not self.utm_campaign:
            self.utm_campaign = self.campaign.slug
        super().save(*args, **kwargs)

    def utm_params(self):
        params = {
            "utm_source": self.utm_source,
            "utm_medium": self.utm_medium,
            "utm_campaign": self.utm_campaign,
        }
        if self.utm_content:
            params["utm_content"] = self.utm_content
        if self.utm_term:
            params["utm_term"] = self.utm_term
        return params

    def build_url(self, base_url: str) -> str:
        base = urljoin(base_url.rstrip("/") + "/", self.landing_path.lstrip("/"))
        return f"{base}?{urlencode(self.utm_params())}"

    def __str__(self):
        return f"{self.campaign.name} • {self.channel}"
