from django.db import models


class Document(models.Model):
    file = models.FileField(upload_to="pdfs/")
    original_filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self) -> str:
        return self.original_filename


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
