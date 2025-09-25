from django.contrib import admin
from .models import FinancialMetric

@admin.register(FinancialMetric)
class FinancialMetricAdmin(admin.ModelAdmin):
    list_display = ("name", "value", "year")
    list_filter = ("year",)
    search_fields = ("name",)
