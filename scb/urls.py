# scb/urls.py
from django.contrib import admin
from django.urls import path, include
from . import views  # home, signup
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("admin/", admin.site.urls),

    # Homepage -> přesměruje na dashboard
    path("", views.home, name="home"),
    path("signup/", views.signup, name="signup"),

    # Aplikace
    path("ingestion/", include(("ingestion.urls", "ingestion"), namespace="ingestion")),
    path("dashboard/", include(("dashboard.urls", "dashboard"), namespace="dashboard")),
    
    path("login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
]
