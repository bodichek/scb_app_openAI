from django.urls import path
from . import views

app_name = "ingestion"

urlpatterns = [
    path("upload/", views.upload_pdf, name="upload"),
    path("documents/", views.documents, name="documents"),
    path("document/<int:doc_id>/", views.document_detail, name="document_detail"),
    path("table/<int:table_id>/", views.table_detail, name="table_detail"),
    path("document/<int:doc_id>/delete/", views.delete_document, name="delete_document"),
    path("table/<int:table_id>/delete/", views.delete_table, name="delete_table"),
]
