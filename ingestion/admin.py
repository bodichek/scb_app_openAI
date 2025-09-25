from django.contrib import admin
from .models import Document, ExtractedTable, ExtractedRow


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "original_filename",
        "doc_type",
        "year",
        "owner",
        "uploaded_at",
    )
    list_filter = ("doc_type", "year", "uploaded_at", "owner")
    search_fields = ("original_filename", "notes", "owner__username")
    date_hierarchy = "uploaded_at"
    ordering = ("-uploaded_at",)


class ExtractedRowInline(admin.TabularInline):
    model = ExtractedRow
    fields = ("code", "value", "section", "raw_data")
    readonly_fields = ("code", "value", "section", "raw_data")
    extra = 0
    show_change_link = True


@admin.register(ExtractedTable)
class ExtractedTableAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "document",
        "page_number",
        "table_index",
        "method",
        "created_at",
    )
    list_filter = ("method", "created_at")
    search_fields = ("document__original_filename",)
    inlines = [ExtractedRowInline]
    ordering = ("-created_at",)


@admin.register(ExtractedRow)
class ExtractedRowAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "code", "value", "section", "created_at")
    list_filter = ("section",)
    search_fields = ("code", "value", "section")
    ordering = ("code",)
