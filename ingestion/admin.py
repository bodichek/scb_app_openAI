from django.contrib import admin
from .models import Document, ExtractedTable, ExtractedRow


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "original_filename", "doc_type", "year", "uploaded_at")
    list_filter = ("doc_type", "year")
    search_fields = ("original_filename",)


@admin.register(ExtractedTable)
class ExtractedTableAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "page_number", "table_index", "method")


@admin.register(ExtractedRow)
class ExtractedRowAdmin(admin.ModelAdmin):
    list_display = ("id", "table")
