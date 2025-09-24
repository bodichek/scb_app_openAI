from django.contrib import admin
from .models import Document, ExtractedTable, ExtractedRow


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "original_filename", "uploaded_at")


@admin.register(ExtractedTable)
class ExtractedTableAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "page_number", "table_index", "method")


@admin.register(ExtractedRow)
class ExtractedRowAdmin(admin.ModelAdmin):
    list_display = ("id", "table")
