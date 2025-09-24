from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from django.db.models.signals import post_delete
from django.dispatch import receiver
import os


def upload_to_document(instance: "Document", filename: str) -> str:
    user_part = f"user_{instance.owner_id or 'anon'}"
    year_part = str(instance.year or "unknown")
    type_part = instance.doc_type or "unknown"
    return f"pdfs/{user_part}/{year_part}/{type_part}/{filename}"


class Document(models.Model):
    class DocType(models.TextChoices):
        BALANCE = "balance", _("Rozvaha")
        INCOME = "income", _("Výsledovka")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True,
    )
    file = models.FileField(upload_to=upload_to_document)
    original_filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    # Nová pole dle požadavku
    doc_type = models.CharField(max_length=20, choices=DocType.choices, null=True, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    
    def __str__(self) -> str:
        return f"{self.original_filename} ({self.get_doc_type_display()} {self.year})"


class ExtractedTable(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="tables")
    page_number = models.IntegerField()
    table_index = models.IntegerField()
    method = models.CharField(max_length=50)
    columns = models.JSONField(default=list)
    meta = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Table {self.table_index} (p{self.page_number}) from {self.document}"


class ExtractedRow(models.Model):
    table = models.ForeignKey(ExtractedTable, on_delete=models.CASCADE, related_name="rows")
    data = models.JSONField(default=dict)

    def __str__(self) -> str:
        return f"Row for {self.table_id}"

@receiver(post_delete, sender=Document)
def delete_document_file(sender, instance, **kwargs):
    """Při smazání Document smaže i soubor z disku."""
    if instance.file and os.path.isfile(instance.file.path):
        try:
            os.remove(instance.file.path)
        except Exception:
            pass