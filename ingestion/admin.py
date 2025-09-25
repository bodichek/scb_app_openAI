from django.contrib import admin
from .models import Document, ExtractedTable, ExtractedRow


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "original_filename", "doc_type", "year", "owner", "uploaded_at")
    list_filter = ("doc_type", "year", "uploaded_at", "owner")
    search_fields = ("original_filename", "notes", "owner__username")
    date_hierarchy = "uploaded_at"
    ordering = ("-uploaded_at",)


@admin.register(ExtractedTable)
class ExtractedTableAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "page_number", "table_index", "method", "created_at")
    list_filter = ("method", "page_number", "created_at")
    search_fields = ("document__original_filename",)
    ordering = ("document", "page_number", "table_index")


@admin.register(ExtractedRow)
class ExtractedRowAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "code", "value")
    list_filter = ("table__document__doc_type", "table__document__year")
    search_fields = ("code", "value", "table__document__original_filename")
    ordering = ("table", "code")
