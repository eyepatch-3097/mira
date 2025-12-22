from django.utils import timezone
from django.db.models import F
from campaigns.models import CampaignLink
from .models import PageView

UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"]

def _extract_utm(request):
    return {k: (request.GET.get(k, "") or "").strip() for k in UTM_KEYS}

def _match_campaign_link(utm):
    if not utm.get("utm_campaign"):
        return None
    qs = CampaignLink.objects.filter(
        utm_campaign=utm["utm_campaign"],
        utm_medium=utm.get("utm_medium", ""),
    )
    if not utm.get("utm_medium"):
        qs = CampaignLink.objects.filter(utm_campaign=utm["utm_campaign"])
    return qs.order_by("-created_at").first()

def log_pageview(request, path: str):
    utm = _extract_utm(request)
    ref = request.META.get("HTTP_REFERER", "")[:500]
    ua = request.META.get("HTTP_USER_AGENT", "")[:300]
    link = _match_campaign_link(utm)

    PageView.objects.create(
        path=path,
        referrer=ref,
        user_agent=ua,
        campaign_link=link,
        **utm
    )

    if link:
        CampaignLink.objects.filter(pk=link.pk).update(
            local_pageviews=F("local_pageviews") + 1,
            last_seen_at=timezone.now(),
        )
