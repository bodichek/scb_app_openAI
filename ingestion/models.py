from __future__ import annotations
from django.db import models
from django.utils import timezone
from django.conf import settings
import os

def _delete_file(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

class Document(models.Model):
    file = models.FileField(upload_to="documents/%Y/%m/%d/")
    original_filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(default=timezone.now, db_index=True)
    year = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    doc_type = models.CharField(
        max_length=20,
        choices=[("balance", "Rozvaha / Balance sheet"), ("income", "Výsledovka / Income statement")],
        db_index=True,
    )
    notes = models.TextField(blank=True, null=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents")

    class Meta:
        indexes = [
            models.Index(fields=["owner", "year", "doc_type"]),
        ]

    def __str__(self):
        return f"{self.original_filename} ({self.year}, {self.doc_type})"

    def delete(self, *args, **kwargs):
        # smazat soubor z úložiště
        path = getattr(self.file, "path", None)
        super().delete(*args, **kwargs)
        if path:
            _delete_file(path)

class ExtractedTable(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="tables")
    page_number = models.PositiveIntegerField(default=1)
    table_index = models.PositiveIntegerField(default=1)
    method = models.CharField(max_length=50, default="gpt-4o-mini")
    columns = models.JSONField(default=list)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["document", "page_number"])]

class ExtractedRow(models.Model):
    table = models.ForeignKey(ExtractedTable, on_delete=models.CASCADE, related_name="rows")
    code = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    label = models.CharField(max_length=255, null=True, blank=True)
    value = models.FloatField(null=True, blank=True, db_index=True)
    section = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    raw_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["section"]),
            models.Index(fields=["value"]),
        ]

# Normalizovaná tabulka (přepsaná) – klíčem je VŽDY číslo řádku (code)
class FinancialMetric(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="metrics")
    code = models.CharField(max_length=50, db_index=True)     # číslo řádku (např. "001", "02", "IV")
    label = models.CharField(max_length=255, blank=True, default="")  # původní label z řádku
    value = models.FloatField(null=True, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    is_derived = models.BooleanField(default=False)           # True = dopočítaná metrika
    derived_key = models.CharField(max_length=100, blank=True, default="")  # např. "gross_margin"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["year"]),
            models.Index(fields=["is_derived"]),
            models.Index(fields=["derived_key"]),
        ]

    def __str__(self):
        if self.is_derived:
            return f"[DERIVED] {self.derived_key}={self.value} ({self.year})"
        return f"{self.code}={self.value} ({self.year})"
