from django.contrib import admin
from .models import Document, ExtractedTable, ExtractedRow, FinancialMetric

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id","original_filename","owner","year","doc_type","uploaded_at")
    list_filter = ("doc_type","year","owner")
    search_fields = ("original_filename",)

@admin.register(ExtractedTable)
class ExtractedTableAdmin(admin.ModelAdmin):
    list_display = ("id","document","method","page_number","table_index","created_at")
    list_filter = ("method",)

@admin.register(ExtractedRow)
class ExtractedRowAdmin(admin.ModelAdmin):
    list_display = ("id","table","code","label","value","section","created_at")
    list_filter = ("section",)
    search_fields = ("code","label")

@admin.register(FinancialMetric)
class FinancialMetricAdmin(admin.ModelAdmin):
    list_display = ("id","document","code","derived_key","value","is_derived","year","created_at")
    list_filter = ("is_derived","year")
    search_fields = ("code","derived_key","label")
