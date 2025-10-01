from __future__ import annotations

import io
import os
import json
import base64
from typing import Dict, List

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt

# ReportLab – export do PDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Image

from ingestion.models import Document, FinancialStatement

# -----------------------------------------------------------
# Hlavní dashboard
# -----------------------------------------------------------
@login_required(login_url="/login/")
def index(request):
    """Základní dashboard – vývoj vybraných metrik a přehled rozvahy."""
    statements = FinancialStatement.objects.filter(owner=request.user).order_by("year")
    years = [s.year for s in statements]

    # připravíme data pro grafy
    income_series = {
        "Revenue": [s.data.get("Revenue", 0) for s in statements],
        "EBIT": [s.data.get("GrossMargin", 0) - s.data.get("Depreciation", 0) for s in statements],
        "NetProfit": [s.data.get("NetProfit", 0) for s in statements],
    }

    # rozvaha pro poslední rok
    selected_year = request.GET.get("year")
    if selected_year and selected_year.isdigit():
        selected_year = int(selected_year)
        selected_statement = statements.filter(year=selected_year).first()
    else:
        selected_statement = statements.last()
        selected_year = selected_statement.year if selected_statement else None

    balance_assets, balance_liabilities = [], []
    if selected_statement:
        data = selected_statement.data
        balance_assets = [
            {"label": "Total Assets", "value": data.get("TotalAssets", 0)},
            {"label": "Current Assets", "value": data.get("CurrentAssets", 0)},
            {"label": "Fixed Assets", "value": data.get("FixedAssets", 0)},
            {"label": "Cash", "value": data.get("Cash", 0)},
            {"label": "Receivables", "value": data.get("Receivables", 0)},
            {"label": "Inventory", "value": data.get("Inventory", 0)},
        ]
        balance_liabilities = [
            {"label": "Total Liabilities", "value": data.get("TotalLiabilities", 0)},
            {"label": "Short Term Liabilities", "value": data.get("ShortTermLiabilities", 0)},
            {"label": "Long Term Loans", "value": data.get("LongTermLoans", 0)},
            {"label": "Short Term Loans", "value": data.get("ShortTermLoans", 0)},
            {"label": "Trade Payables", "value": data.get("TradePayables", 0)},
        ]

    return render(
        request,
        "dashboard/index.html",
        {
            "years": years,
            "income_series": income_series,
            "balance_assets": balance_assets,
            "balance_liabilities": balance_liabilities,
            "selected_year": selected_year,
        },
    )

# -----------------------------------------------------------
# Profitability Dashboard
# -----------------------------------------------------------
@login_required(login_url="/login/")
def profitability_dashboard(request):
    """Profitability dashboard – vývoj metrik a ukazatelů v čase."""
    statements = FinancialStatement.objects.filter(owner=request.user).order_by("year")
    years = [s.year for s in statements]

    def as_list(key: str) -> list:
        return [s.data.get(key, 0) for s in statements]

    context = {
        "years": years,
        "Revenue": as_list("Revenue"),
        "GrossMargin": as_list("GrossMargin"),
        "NetProfit": as_list("NetProfit"),
        "Depreciation": as_list("Depreciation"),
        "InterestPaid": as_list("InterestPaid"),
        "IncomeTax": as_list("IncomeTax"),
    }

    return render(request, "dashboard/profitability.html", context)

# -----------------------------------------------------------
# Report View (HTML tabulka)
# -----------------------------------------------------------
@login_required(login_url="/login/")
def report_view(request):
    statements = FinancialStatement.objects.filter(owner=request.user).order_by("year")
    return render(request, "dashboard/report.html", {"statements": statements})

# -----------------------------------------------------------
# Export do PDF (grafy + tabulky)
# -----------------------------------------------------------
@login_required(login_url="/login/")
def export_pdf(request):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20
    )

    styles = getSampleStyleSheet()
    elements: List = []

    elements.append(Paragraph("📊 Profitability Report", styles["Heading1"]))
    elements.append(Spacer(1, 12))

    # vložení grafů z POST base64
    for key, title in [
        ("main_chart", "Hlavní metriky"),
        ("margins_chart", "Marže (%) – vývoj"),
        ("cash_chart", "Cash Flow"),
    ]:
        b64 = request.POST.get(key)
        if b64 and b64.startswith("data:image"):
            try:
                header, data = b64.split(",", 1)
                imgdata = base64.b64decode(data)
                img = Image(io.BytesIO(imgdata))
                img.drawHeight = 250
                img.drawWidth = 500
                elements.append(Paragraph(title, styles["Heading2"]))
                elements.append(img)
                elements.append(Spacer(1, 20))
            except Exception:
                pass

    # data z FinancialStatement
    statements = FinancialStatement.objects.filter(owner=request.user).order_by("year")
    years = [s.year for s in statements]

    header = ["Metric"] + [str(y) for y in years]
    profit_rows = [
        ["Revenue"] + [s.data.get("Revenue", 0) for s in statements],
        ["Gross Margin"] + [s.data.get("GrossMargin", 0) for s in statements],
        ["Net Profit"] + [s.data.get("NetProfit", 0) for s in statements],
    ]

    data = [header] + profit_rows
    table = Table(data, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4a90e2")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    elements.append(Paragraph("📑 Tabulka Profitability", styles["Heading2"]))
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename="profitability_report.pdf")

# -----------------------------------------------------------
# Uložení grafů z prohlížeče (Chart.js)
# -----------------------------------------------------------
@login_required(login_url="/login/")
@csrf_exempt
def save_chart(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "msg": "Only POST allowed"}, status=400)

    try:
        data = json.loads(request.body)
    except Exception as e:
        return JsonResponse({"status": "error", "msg": f"Invalid JSON: {e}"}, status=400)

    charts_dir = os.path.join(settings.MEDIA_ROOT, "charts")
    os.makedirs(charts_dir, exist_ok=True)

    saved = []
    for name, img_data in data.items():
        try:
            if img_data.startswith("data:image/png;base64,"):
                img_data = img_data.split(",", 1)[1]
            img_bytes = base64.b64decode(img_data)
            out_path = os.path.join(charts_dir, f"{name}.png")
            with open(out_path, "wb") as f:
                f.write(img_bytes)
            saved.append(name)
        except Exception:
            pass

    return JsonResponse({"status": "ok", "saved": saved})
