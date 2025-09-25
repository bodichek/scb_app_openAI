# dashboard/views.py
import io
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# správný import z ingestion
from ingestion.models import Document, ExtractedRow, FinancialMetric


@login_required(login_url="/login/")
def dashboard(request):
    """
    Hlavní dashboard – vývoj vybraných metrik a rozvaha podle zvoleného roku.
    """
    docs = Document.objects.filter(owner=request.user).order_by("year")
    years = sorted({d.year for d in docs if d.year})

    # --- Vývoj příjmů (Revenue, EBIT, Net Profit) ---
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

    # --- Rozvaha podle zvoleného roku ---
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


@login_required(login_url="/login/")
def metrics_dashboard(request):
    """
    Detailní dashboard: nahrané dokumenty, extrahované řádky a metriky.
    Připraví data pro grafy (výnosy a náklady podle roku).
    """
    docs = Document.objects.filter(owner=request.user).order_by("-year")
    rows = ExtractedRow.objects.filter(table__document__owner=request.user)
    metrics = FinancialMetric.objects.filter(document__owner=request.user)

    # Výnosy podle roku
    revenue_by_year = {}
    for m in metrics:
        if m.metric_key == "revenue":
            revenue_by_year[m.document.year] = m.value

    # Náklady podle roku
    costs_by_year = {}
    for m in metrics:
        if m.metric_key == "costs":
            costs_by_year[m.document.year] = m.value

    context = {
        "documents": docs,
        "rows": rows,
        "metrics": metrics,
        "revenue_by_year": revenue_by_year,
        "costs_by_year": costs_by_year,
    }

    return render(request, "dashboard/metrics_dashboard.html", context)


@login_required(login_url="/login/")
def export_pdf(request):
    """
    Export všech finančních metrik do PDF.
    """
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)

    # Nadpis
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 800, "Přehled finančních metrik")

    # Načtení metrik
    metrics = FinancialMetric.objects.filter(document__owner=request.user).order_by("year", "metric_key")
    y = 760
    p.setFont("Helvetica", 12)
    for m in metrics:
        label = m.label if hasattr(m, "label") and m.label else m.metric_key
        p.drawString(100, y, f"{label} ({m.year}): {m.value}")
        y -= 20

        # nová stránka, když dojdeme dolů
        if y < 100:
            p.showPage()
            p.setFont("Helvetica", 12)
            y = 800

    # Dokončení PDF
    p.showPage()
    p.save()
    buffer.seek(0)

    return FileResponse(buffer, as_attachment=True, filename="financial_metrics.pdf")
