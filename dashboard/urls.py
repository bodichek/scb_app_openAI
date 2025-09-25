from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    # hlavní dashboard
    path("", views.dashboard, name="dashboard"),

    # profitability grafy
    path("profitability/", views.profitability_dashboard, name="profitability_dashboard"),

    # report
    path("report/", views.report_view, name="report_view"),

    # export PDF
    path("export-pdf/", views.export_pdf, name="export_pdf"),
]
