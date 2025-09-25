from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from ingestion.models import FinancialMetric, Document

@login_required(login_url="/login/")
def dashboard(request):
    docs = Document.objects.filter(owner=request.user).order_by("year")
    years = sorted({d.year for d in docs if d.year})

    # --- Income vývoj ---
    tracked_income = ["revenue", "ebit", "net_profit"]
    income_series = {k: [] for k in tracked_income}

    for y in years:
        for key in tracked_income:
            val = FinancialMetric.objects.filter(
                document__owner=request.user,
                year=y,
                derived_key=key,
                is_derived=True
            ).first()
            income_series[key].append(val.value if val else None)

    # --- Balance podle zvoleného roku ---
    selected_year = request.GET.get("year")
    if selected_year and selected_year.isdigit():
        selected_year = int(selected_year)
    else:
        selected_year = years[-1] if years else None

    balance_assets, balance_liabilities = [], []
    if selected_year:
        metrics = FinancialMetric.objects.filter(
            document__owner=request.user,
            year=selected_year,
            document__doc_type="balance",
            is_derived=False
        ).exclude(value__isnull=True)

        for m in metrics:
            label = (m.label or "").lower()
            if "aktiv" in label:
                balance_assets.append({"label": m.label, "value": m.value})
            elif "pasiv" in label:
                balance_liabilities.append({"label": m.label, "value": m.value})

    return render(request, "dashboard/index.html", {
        "years": years,
        "income_series": income_series,
        "balance_assets": balance_assets,
        "balance_liabilities": balance_liabilities,
        "selected_year": selected_year,
    })
