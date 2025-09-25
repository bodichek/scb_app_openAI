from django.urls import path
from . import views

app_name = "company"

urlpatterns = [
    path("identification/", views.company_identification, name="identification"),
    path("success/", views.success, name="success"),
]
