from django.contrib.admin import AdminSite

class MiraSuperAdmin(AdminSite):
    site_header = "Mira SuperAdmin"
    site_title = "Mira SuperAdmin"
    index_title = "Campaigns & Funnel Controls"

superadmin_site = MiraSuperAdmin(name="mira_superadmin")
