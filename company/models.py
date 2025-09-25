import uuid
from django.db import models
from django.utils import timezone


class Company(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # unikátní ID
    company_name = models.CharField("Název firmy", max_length=255)
    respondent_name = models.CharField("Jméno účastníka", max_length=255)   # 🆕
    respondent_email = models.EmailField("Email respondenta")
    phone = models.CharField("Telefonní číslo", max_length=20, blank=True, null=True)  # 🆕
    about = models.TextField("Informace o sobě / poznámka", blank=True, null=True)     # 🆕

    ico = models.CharField("IČO", max_length=20, blank=True, null=True)
    industry = models.CharField("Odvětví", max_length=255, blank=True, null=True)

    COMPANY_SIZE_CHOICES = [
        ("micro", "Mikro (1–10 zaměstnanců)"),
        ("small", "Malá (11–50 zaměstnanců)"),
        ("medium", "Střední (51–250 zaměstnanců)"),
        ("large", "Velká (250+ zaměstnanců)"),
    ]
    company_size = models.CharField("Velikost firmy", max_length=20, choices=COMPANY_SIZE_CHOICES)

    COACH_CHOICES = [
        ("coach1", "Kouč 1"),
        ("coach2", "Kouč 2"),
        ("coach3", "Kouč 3"),
    ]
    coach = models.CharField("Kouč", max_length=50, choices=COACH_CHOICES)

    created_at = models.DateTimeField("Datum zpracování", default=timezone.now)

    def __str__(self):
        return f"{self.company_name} ({self.respondent_name})"
