from django.db import models
from django.contrib.auth.models import User
import uuid

class OpenAnswer(models.Model):
    SECTION_CHOICES = [
        ("VÍCE ČASU", "VÍCE ČASU"),
        ("VÍCE PENĚZ", "VÍCE PENĚZ"),
        ("MÉNĚ STRACHU", "MÉNĚ STRACHU"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    batch_id = models.UUIDField(default=uuid.uuid4, db_index=True)  # skupina odpovědí jednoho odeslání
    section = models.CharField(max_length=32, choices=SECTION_CHOICES)
    question = models.TextField()
    answer = models.TextField()
    ai_response = models.TextField(blank=True, null=True)  # stejné shrnutí uložíme ke každé odpovědi v batchi
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["batch_id"]),
        ]

    def __str__(self):
        return f"{self.user} | {self.section} | {self.question[:40]}..."
