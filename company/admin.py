from django.contrib import admin
from .models import Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "company_name",
        "respondent_name",
        "respondent_email",
        "phone",
        "ico",
        "industry",
        "company_size",
        "coach",
        "created_at",
    )
    list_filter = ("company_size", "coach", "created_at")
    search_fields = (
        "company_name",
        "respondent_name",
        "respondent_email",
        "phone",
        "ico",
        "industry",
    )
    ordering = ("-created_at",)
