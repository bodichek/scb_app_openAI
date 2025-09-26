from django.urls import path
from . import views

app_name = "hodnoty"

urlpatterns = [
    path("", views.values_list, name="list"),
]