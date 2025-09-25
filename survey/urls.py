from django.urls import path
from . import views

app_name = "survey"

urlpatterns = [
    path("", views.questionnaire, name="questionnaire"),
    path("summary/", views.survey_summary, name="summary"),  # 🔹 nový view
    path("detail/<uuid:batch_id>/", views.survey_detail, name="detail"),
]

