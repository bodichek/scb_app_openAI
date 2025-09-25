from django.db import models

class FinancialMetric(models.Model):
    name = models.CharField(max_length=100)                 # název metriky (např. Tržby, Náklady)
    value = models.DecimalField(max_digits=15, decimal_places=2)  # hodnota metriky
    year = models.IntegerField()                            # rok

    def __str__(self):
        return f"{self.name} ({self.year}): {self.value}"
