from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    # hlavní dashboard
    path("", views.dashboard, name="index"),  # 👈 sjednoceno na 'index'

    # nahrané hodnoty
    path("metrics/", views.metrics_dashboard, name="metrics"),

    # profitability grafy
    path("profitability/", views.profitability_dashboard, name="profitability"),

    # report
    path("report/", views.report_view, name="report"),

    # export PDF
    path("export-pdf/", views.export_pdf, name="export_pdf"),
]
