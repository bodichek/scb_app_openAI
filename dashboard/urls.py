# dashboard/urls.py
from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard, name="index"),       # name="index" kvůli redirectům
    path("metrics/", views.metrics_dashboard, name="metrics"),
    path("export_pdf/", views.export_pdf, name="export_pdf"),
]
