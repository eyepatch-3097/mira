from django.urls import path
from .views import signup, MiraLoginView, MiraLogoutView, dashboard, edit_profile, data_sources

urlpatterns = [
    path("signup/", signup, name="signup"),
    path("login/", MiraLoginView.as_view(), name="login"),
    path("logout/", MiraLogoutView.as_view(), name="logout"),
    path("dashboard/", dashboard, name="dashboard"),
    path("profile/edit/", edit_profile, name="edit_profile"),
    path("data-sources/", data_sources, name="data_sources"),
]
