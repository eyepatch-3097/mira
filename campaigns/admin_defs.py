from django.contrib import admin
from django.conf import settings
from django.utils.html import format_html
from .models import Campaign, CampaignLink

class CampaignLinkInline(admin.TabularInline):
    model = CampaignLink
    extra = 1
    fields = ("channel", "landing_path", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
              "total_sent", "total_replies", "posthog_visits")
    readonly_fields = ()

@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")
    inlines = [CampaignLinkInline]

@admin.register(CampaignLink)
class CampaignLinkAdmin(admin.ModelAdmin):
    list_display = ("campaign", "channel", "utm_campaign", "total_sent", "total_replies",
                    "local_pageviews", "posthog_visits", "last_seen_at", "link")
    list_filter = ("channel",)
    search_fields = ("campaign__name", "utm_campaign", "utm_content")
    list_editable = ("total_sent", "total_replies", "posthog_visits")
    readonly_fields = ("local_pageviews", "last_seen_at")

    def link(self, obj):
        url = obj.build_url(settings.SITE_BASE_URL)
        return format_html('<a href="{}" target="_blank">Open link</a>', url)

    link.short_description = "UTM Link"
