from __future__ import annotations
import json, base64
from io import BytesIO

from django.shortcuts import render
from django.http import HttpRequest, HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils.safestring import mark_safe

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet

from ingestion.models import Document
from .utils import calculate_metrics, calculate_growth


@login_required
def metrics_dashboard(request: HttpRequest) -> HttpResponse:
    user = request.user
    years = (
        Document.objects.filter(owner=user)
        .values_list("year", flat=True)
        .distinct()
        .order_by("year")
    )

    metrics_by_year: dict[int, dict] = {}
    for y in years:
        if y is None:
            continue
        metrics_by_year[y] = calculate_metrics(user, y)

    growth_by_year = calculate_growth(metrics_by_year)

    chart_data = {
        "years": list(metrics_by_year.keys()),
        "revenue":      [metrics_by_year[y]["Revenue"] for y in metrics_by_year],
        "cogs":         [metrics_by_year[y]["COGS"] for y in metrics_by_year],
        "gross_margin": [metrics_by_year[y]["Gross_Margin"] for y in metrics_by_year],
        "overheads":    [metrics_by_year[y]["Overheads"] for y in metrics_by_year],
        "op_profit":    [metrics_by_year[y]["Operating_Profit"] for y in metrics_by_year],
        "net_profit":   [metrics_by_year[y]["Net_Profit"] for y in metrics_by_year],
        "revenue_growth":   [growth_by_year.get(y, {}).get("Revenue_Growth", 0) for y in metrics_by_year],
        "cogs_growth":      [growth_by_year.get(y, {}).get("COGS_Growth", 0) for y in metrics_by_year],
        "overheads_growth": [growth_by_year.get(y, {}).get("Overheads_Growth", 0) for y in metrics_by_year],
        "op_profit_pct":    [growth_by_year.get(y, {}).get("Operating_Profit_Pct", 0) for y in metrics_by_year],
        "net_profit_pct":   [growth_by_year.get(y, {}).get("Net_Profit_Pct", 0) for y in metrics_by_year],
        # rozvaha – připravené k použití v případných grafech
        "assets_total": [metrics_by_year[y]["Assets_Total"] for y in metrics_by_year],
        "liab_total":   [metrics_by_year[y]["Liabilities_Total"] for y in metrics_by_year],
        "equity":       [metrics_by_year[y]["Equity"] for y in metrics_by_year],
        "cash":         [metrics_by_year[y]["Cash"] for y in metrics_by_year],
    }

    return render(request, "dashboard/metrics.html", {
        "metrics_by_year": metrics_by_year,
        "growth_by_year": growth_by_year,
        "chart_data": mark_safe(json.dumps(chart_data)),
    })


@login_required
def export_pdf(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponse("Invalid request", status=400)

    charts_data = request.POST.get("charts_data")
    charts = json.loads(charts_data) if charts_data else {}

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = [Paragraph("📊 Financial Dashboard Report", styles["Heading1"]), Spacer(1, 12)]

    for title, img_b64 in charts.items():
        try:
            if "," in img_b64:
                img_b64 = img_b64.split(",", 1)[1]
            img_bytes = base64.b64decode(img_b64)
            img = Image(BytesIO(img_bytes))
            img._restrictSize(500, 300)
            elements.append(Paragraph(title, styles["Heading2"]))
            elements.append(img)
            elements.append(Spacer(1, 18))
        except Exception as e:
            elements.append(Paragraph(f"Chyba načítání grafu: {e}", styles["Normal"]))
            elements.append(Spacer(1, 8))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()

    resp = HttpResponse(content_type="application/pdf")
    resp["Content-Disposition"] = 'attachment; filename="financial_report.pdf"'
    resp.write(pdf)
    return resp
