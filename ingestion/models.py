from django.db import models
from django.contrib.auth.models import User


class Document(models.Model):
    """Uložený soubor PDF (výkaz)."""
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to="documents/")
    year = models.IntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.file.name} ({self.year})"


class FinancialStatement(models.Model):
    """Výsledky analýzy PDF (parsované OpenAI)."""
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    year = models.IntegerField()
    data = models.JSONField()  # uložené metriky jako JSON
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("owner", "year")

    def __str__(self):
        return f"{self.owner.username} - {self.year}"
