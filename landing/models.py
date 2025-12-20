from django.db import models
from campaigns.models import CampaignLink

class PageView(models.Model):
    path = models.CharField(max_length=300)
    referrer = models.CharField(max_length=500, blank=True)

    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=140, blank=True)
    utm_content = models.CharField(max_length=140, blank=True)
    utm_term = models.CharField(max_length=140, blank=True)

    campaign_link = models.ForeignKey(CampaignLink, null=True, blank=True, on_delete=models.SET_NULL)

    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.path} @ {self.created_at}"
