from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "dashboard"

urlpatterns = [
path("", views.metrics_dashboard, name="metrics_dashboard"),
path("metrics/", views.metrics_dashboard, name="metrics"),
path("export_pdf/", views.export_pdf, name="export_pdf"),
]
