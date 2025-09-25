from django.conf import settings
from django.db import models
from django.utils import timezone


class Document(models.Model):
    """Nahraný PDF dokument (rozvaha/výsledovka atd.)."""

    DOC_TYPES = [
        ("balance", "Rozvaha / Balance sheet"),
        ("income", "Výsledovka / Income statement"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    file = models.FileField(upload_to="documents/%Y/%m/%d/")
    original_filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(default=timezone.now, db_index=True)

    year = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    doc_type = models.CharField(max_length=20, choices=DOC_TYPES, db_index=True)
    notes = models.TextField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.doc_type}, {self.year})"


class ExtractedTable(models.Model):
    """Tabulka vytažená z PDF."""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="tables",
    )

    page_number = models.PositiveIntegerField(default=1)
    table_index = models.PositiveIntegerField(default=1)
    method = models.CharField(max_length=50, default="merged")

    columns = models.JSONField(default=list)
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["document", "page_number"]),
        ]

    def __str__(self) -> str:
        return f"Table {self.id} (doc={self.document_id}, page={self.page_number})"


class ExtractedRow(models.Model):
    """Řádek tabulky – kód, popis, hodnota."""

    table = models.ForeignKey(
        ExtractedTable,
        on_delete=models.CASCADE,
        related_name="rows",
    )

    code = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    label = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    value = models.FloatField(null=True, blank=True, db_index=True)
    section = models.CharField(max_length=50, null=True, blank=True, db_index=True)

    raw_data = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["label"]),
            models.Index(fields=["section"]),
            models.Index(fields=["value"]),
        ]

    def __str__(self) -> str:
        return f"Row {self.id} (code={self.code}, label={self.label}, value={self.value})"
