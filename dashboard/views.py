from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from ingestion.models import FinancialStatement


@login_required
def index(request):
    """Dashboard – zobrazí všechny výkazy uživatele."""
    statements = FinancialStatement.objects.filter(owner=request.user).order_by("year")
    return render(request, "dashboard/index.html", {"statements": statements})
