from internal_admin.admin_site import superadmin_site
from django.contrib import admin
from campaigns.models import Campaign, CampaignLink
from campaigns.admin_defs import CampaignAdmin, CampaignLinkAdmin

# Register on the *custom* admin site
superadmin_site.register(Campaign, CampaignAdmin)
superadmin_site.register(CampaignLink, CampaignLinkAdmin)
