from django.urls import path
from . import views

app_name = "dashboard"   # 👈 Tohle je důležité pro namespaces

urlpatterns = [
    path("", views.index, name="index"),
]
