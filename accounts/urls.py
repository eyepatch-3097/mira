from django.urls import path
from .views import signup, MiraLoginView, MiraLogoutView, dashboard

urlpatterns = [
    path("signup/", signup, name="signup"),
    path("login/", MiraLoginView.as_view(), name="login"),
    path("logout/", MiraLogoutView.as_view(), name="logout"),
    path("dashboard/", dashboard, name="dashboard"),
]
