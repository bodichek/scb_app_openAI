from django.db import models
from django.contrib.auth.models import User
import uuid


class SurveySubmission(models.Model):
    """
    Každé odeslání dotazníku je jedna submission.
    Uchovává info o uživateli a datu vytvoření.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    batch_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Dotazník {self.user.username} ({self.created_at:%d.%m.%Y %H:%M})"


class Response(models.Model):
    """
    Jedna odpověď na konkrétní otázku dotazníku.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    submission = models.ForeignKey(
        SurveySubmission,
        on_delete=models.CASCADE,
        related_name="responses"
    )
    question = models.TextField()
    score = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user.username} – {self.question[:50]}... → {self.score}"
