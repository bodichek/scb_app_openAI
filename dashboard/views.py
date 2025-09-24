import json, base64, re
from io import BytesIO
import pandas as pd
from django.shortcuts import render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils.safestring import mark_safe
from ingestion.models import Document, ExtractedRow
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet


# 🔹 Pomocná funkce – najdi hodnotu podle čísla řádku
def _get_value(rows, row_number: int):
    for r in rows:
        if str(r.get("slo_dku_c")) == str(row_number):
            for v in r.values():
                if isinstance(v, (int, float)):
                    return v
                try:
                    return float(str(v).replace(" ", "").replace(",", "."))
                except Exception:
                    continue
    return 0


@login_required
def index(request):
    """Základní dashboard – jednoduchý přehled výnosy/náklady/zisk a rozvaha."""
    user_docs = Document.objects.filter(owner=request.user)

    income_statements = {}
    balance_sheets = {}

    for doc in user_docs:
        for table in doc.tables.all():
            rows = [r.data for r in ExtractedRow.objects.filter(table=table)]
            if not rows:
                continue
            year = doc.year or "Neznámý rok"

            if doc.doc_type == "income":
                revenue = _get_value(rows, 1) + _get_value(rows, 2)
                costs = _get_value(rows, 4) + _get_value(rows, 5)
                profit = revenue - costs
                income_statements[year] = {
                    "revenue": revenue,
                    "costs": costs,
                    "profit": profit,
                }
            elif doc.doc_type == "balance":
                assets = _get_value(rows, 1)  # příklad, doladí se později
                liabilities = _get_value(rows, 2)
                equity = _get_value(rows, 3)
                balance_sheets[year] = {
                    "assets": assets,
                    "liabilities": liabilities,
                    "equity": equity,
                }

    context = {
        "income_statements": income_statements,
        "balance_sheets": balance_sheets,
    }
    return render(request, "dashboard/index.html", context)


@login_required
def metrics_dashboard(request):
    """Pokročilé metriky a grafy."""
    docs = Document.objects.filter(owner=request.user, doc_type="income")

    metrics_by_year = {}

    for doc in docs:
        rows = [r.data for table in doc.tables.all() for r in table.rows.all()]
        if not rows:
            continue

        revenue = _get_value(rows, 1) + _get_value(rows, 2)
        cogs = _get_value(rows, 4) + _get_value(rows, 5)
        gross_margin = revenue - cogs
        gross_margin_pct = (gross_margin / revenue * 100) if revenue else 0

        overheads = (
            _get_value(rows, 12)
            + _get_value(rows, 13)
            + _get_value(rows, 16)
            + _get_value(rows, 17)
            + _get_value(rows, 18)
        )

        op_profit = gross_margin - overheads
        ebt = op_profit + (_get_value(rows, 20) - _get_value(rows, 21))
        net_profit = ebt - _get_value(rows, 40)

        metrics_by_year[doc.year] = {
            "Revenue": revenue,
            "COGS": cogs,
            "Gross_Margin": gross_margin,
            "Gross_Margin_pct": gross_margin_pct,
            "Overheads": overheads,
            "Operating_Profit": op_profit,
            "Net_Profit": net_profit,
        }

    # 🔹 Meziroční růst
    growth_by_year = {}
    years = sorted(metrics_by_year.keys())
    for i in range(1, len(years)):
        y, y_prev = years[i], years[i - 1]
        m, mp = metrics_by_year[y], metrics_by_year[y_prev]
        growth_by_year[y] = {
            "Revenue_Growth_pct": ((m["Revenue"] - mp["Revenue"]) / mp["Revenue"] * 100) if mp["Revenue"] else 0,
            "COGS_Growth_pct": ((m["COGS"] - mp["COGS"]) / mp["COGS"] * 100) if mp["COGS"] else 0,
            "Overheads_Growth_pct": ((m["Overheads"] - mp["Overheads"]) / mp["Overheads"] * 100) if mp["Overheads"] else 0,
            "Operating_Profit_pct": (m["Operating_Profit"] / m["Revenue"] * 100) if m["Revenue"] else 0,
            "Net_Profit_pct": (m["Net_Profit"] / m["Revenue"] * 100) if m["Revenue"] else 0,
        }

    # 🔹 Data pro grafy
    chart_data = {
        "years": years,
        "revenue": [metrics_by_year[y]["Revenue"] for y in years],
        "cogs": [metrics_by_year[y]["COGS"] for y in years],
        "gross_margin": [metrics_by_year[y]["Gross_Margin"] for y in years],
        "net_profit": [metrics_by_year[y]["Net_Profit"] for y in years],
        "revenue_growth": [growth_by_year.get(y, {}).get("Revenue_Growth_pct", 0) for y in years],
        "cogs_growth": [growth_by_year.get(y, {}).get("COGS_Growth_pct", 0) for y in years],
        "overheads_growth": [growth_by_year.get(y, {}).get("Overheads_Growth_pct", 0) for y in years],
        "op_profit_pct": [growth_by_year.get(y, {}).get("Operating_Profit_pct", 0) for y in years],
        "net_profit_pct": [growth_by_year.get(y, {}).get("Net_Profit_pct", 0) for y in years],
    }

    return render(request, "dashboard/metrics.html", {
        "metrics_by_year": metrics_by_year,
        "growth_by_year": growth_by_year,
        "chart_data": mark_safe(json.dumps(chart_data)),
    })


@login_required
def export_pdf(request):
    """Export grafů do PDF."""
    if request.method == "POST":
        charts_data = request.POST.get("charts_data")
        charts = json.loads(charts_data) if charts_data else {}

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = [Paragraph("📊 Financial Dashboard Report", styles["Heading1"]), Spacer(1, 12)]

        for title, img_base64 in charts.items():
            img_data = base64.b64decode(img_base64.split(",")[1])
            img = Image(BytesIO(img_data))
            img._restrictSize(500, 300)
            elements.append(Paragraph(title, styles["Heading2"]))
            elements.append(img)
            elements.append(Spacer(1, 24))

        doc.build(elements)
        pdf = buffer.getvalue()
        buffer.close()

        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="financial_report.pdf"'
        response.write(pdf)
        return response

    return HttpResponse("Invalid request", status=400)
