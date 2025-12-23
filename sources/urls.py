from django.urls import path
from . import views

urlpatterns = [
    path("sources/", views.sources_list, name="sources_list"),
    path("sources/<int:source_id>/", views.source_detail, name="source_detail"),
    path("sources/<int:source_id>/progress/", views.source_progress, name="source_progress"),

    path("data-sources/website/new/", views.website_source_new, name="website_source_new"),
    path("data-sources/website/<int:source_id>/pages/", views.website_pages_select, name="website_pages_select"),
    path("pages/<int:page_id>/summary/", views.update_page_summary, name="update_page_summary"),
]
