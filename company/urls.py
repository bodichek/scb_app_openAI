from django.urls import path
from . import views

app_name = "company"

urlpatterns = [
    path("", views.company_list, name="list"),   # 🔹 přidáno
    path("identification/", views.identification, name="identification"),
    path("new/", views.company_create, name="create"),
]