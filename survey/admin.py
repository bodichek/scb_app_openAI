from django.contrib import admin
from django.db.models import Avg, Max
from .models import Response


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "question", "score", "created_at")
    list_filter = ("user", "created_at")
    search_fields = ("question", "user__username")

    # Přidáme vlastní stránku s agregovanými výsledky
    change_list_template = "admin/survey/response_changelist.html"

    def changelist_view(self, request, extra_context=None):
        # Souhrnné statistiky
        qs = self.get_queryset(request)
        summary = qs.values("user__username").annotate(
            avg_score=Avg("score"),
            last_submit=Max("created_at")
        ).order_by("-last_submit")

        extra_context = extra_context or {}
        extra_context["summary"] = summary
        return super().changelist_view(request, extra_context=extra_context)
