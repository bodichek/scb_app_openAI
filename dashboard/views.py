# dashboard/views.py
from __future__ import annotations

import io
from typing import Dict, List, Optional

from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import render

# ReportLab – hezký tabulkový export
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ingestion.models import Document, ExtractedRow, FinancialMetric
from ingestion.utils import DERIVED_FORMULAS


# -----------------------------------------------------------------------------
# Společný builder kontextu pro profitability i report
# -----------------------------------------------------------------------------
def build_profitability_context(request):
    """
    Vrátí dictionary se všemi daty pro profitability i report (profit & cash bloky,
    meziroční růsty a pracovní kapitál).
    """
    # --- roky dostupných výsledovek
    income_docs = Document.objects.filter(owner=request.user, doc_type="income").order_by("year")
    years = sorted({d.year for d in income_docs if d.year})

    if not years:
        return {"years": []}

    # Všechny metriky uživatele
    fm = FinancialMetric.objects.filter(document__owner=request.user)

    # Helpers
    def get_derived(year: int, key: str) -> Optional[float]:
        x = fm.filter(year=year, is_derived=True, derived_key=key).first()
        return x.value if x else None

    def sum_raw_codes(year: int, codes: List[str]) -> Optional[float]:
        if not codes:
            return None
        vals = fm.filter(year=year, is_derived=False, code__in=codes).values_list("value", flat=True)
        nums = [float(v) for v in vals if v is not None]
        return sum(nums) if nums else None

    # --- 1) Základní bloky + výpočty
    revenue: Dict[int, Optional[float]] = {}
    cogs: Dict[int, Optional[float]] = {}
    overheads: Dict[int, Optional[float]] = {}
    gross_margin: Dict[int, Optional[float]] = {}
    gross_margin_pct: Dict[int, Optional[float]] = {}
    ebit: Dict[int, Optional[float]] = {}
    net_profit: Dict[int, Optional[float]] = {}

    for y in years:
        revenue[y] = get_derived(y, "revenue")
        cogs[y] = get_derived(y, "cogs")
        overheads[y] = get_derived(y, "overheads")

        gm = (revenue[y] - cogs[y]) if (revenue[y] is not None and cogs[y] is not None) else None
        gross_margin[y] = gm
        gross_margin_pct[y] = (gm / revenue[y] * 100.0) if (gm is not None and revenue[y]) else None

        # EBIT (varianta A): GM - Overheads
        ebit[y] = (gm - overheads[y]) if (gm is not None and overheads[y] is not None) else None

        # Net Profit = EBT - tax; EBT = EBIT + (fin_income - fin_expense)
        fin_income_codes = DERIVED_FORMULAS["income"].get("fin_income", [])
        fin_expense_codes = DERIVED_FORMULAS["income"].get("fin_expense", [])
        tax_codes = DERIVED_FORMULAS["income"].get("tax", [])

        fi = sum_raw_codes(y, fin_income_codes) or 0.0
        fe = sum_raw_codes(y, fin_expense_codes) or 0.0
        tax = sum_raw_codes(y, tax_codes) or 0.0

        ebt = (ebit[y] + fi - fe) if ebit[y] is not None else None
        net_profit[y] = (ebt - tax) if ebt is not None else None

    # --- 2) Meziroční růsty a maržové ukazatele
    def yoy_growth(series: Dict[int, Optional[float]]) -> Dict[int, Optional[float]]:
        out: Dict[int, Optional[float]] = {}
        for i, y in enumerate(years):
            if i == 0:
                out[y] = None
                continue
            prev = years[i - 1]
            if series.get(prev) not in (None, 0) and series.get(y) is not None:
                out[y] = (series[y] - series[prev]) / series[prev] * 100.0
            else:
                out[y] = None
        return out

    revenue_growth_pct = yoy_growth(revenue)
    cogs_growth_pct = yoy_growth(cogs)
    overheads_growth_pct = yoy_growth(overheads)

    operating_profit_pct = {
        y: (ebit[y] / revenue[y] * 100.0) if (ebit[y] is not None and revenue[y]) else None for y in years
    }
    net_profit_pct = {
        y: (net_profit[y] / revenue[y] * 100.0) if (net_profit[y] is not None and revenue[y]) else None for y in years
    }

    # --- 3) Balance položky (pro cash aproximace)
    def bal_by_codes(year: int, codes: List[str]) -> Optional[float]:
        if not codes:
            return None
        vals = fm.filter(year=year, is_derived=False, code__in=codes, document__doc_type="balance").values_list(
            "value", flat=True
        )
        nums = [float(v) for v in vals if v is not None]
        return sum(nums) if nums else None

    inv_codes = DERIVED_FORMULAS.get("balance", {}).get("inventories", [])
    rec_codes = DERIVED_FORMULAS.get("balance", {}).get("receivables_trade", [])
    pay_codes = DERIVED_FORMULAS.get("balance", {}).get("payables_trade", [])

    inventories: Dict[int, Optional[float]] = {}
    receivables: Dict[int, Optional[float]] = {}
    payables: Dict[int, Optional[float]] = {}

    for y in years:
        inventories[y] = bal_by_codes(y, inv_codes)
        receivables[y] = bal_by_codes(y, rec_codes)
        payables[y] = bal_by_codes(y, pay_codes)

    def delta(series: Dict[int, Optional[float]]) -> Dict[int, Optional[float]]:
        out: Dict[int, Optional[float]] = {}
        for i, y in enumerate(years):
            if i == 0:
                out[y] = None
                continue
            prev = years[i - 1]
            if series.get(prev) is not None and series.get(y) is not None:
                out[y] = series[y] - series[prev]
            else:
                out[y] = None
        return out

    d_inventories = delta(inventories)
    d_receivables = delta(receivables)
    d_payables = delta(payables)

    # Cash aproximace
    cash_from_customers = {
        y: (revenue[y] - (d_receivables[y] or 0)) if revenue.get(y) is not None else None for y in years
    }
    cash_to_suppliers = {
        y: (cogs[y] + (d_inventories[y] or 0) - (d_payables[y] or 0)) if cogs.get(y) is not None else None for y in years
    }
    gross_cash_profit = {
        y: (cash_from_customers[y] - cash_to_suppliers[y])
        if (cash_from_customers.get(y) is not None and cash_to_suppliers.get(y) is not None)
        else None
        for y in years
    }

    # OCF ≈ Net Profit + Depreciation (ř. 17) ± Δ Working Capital
    def depreciation(year: int) -> Optional[float]:
        v = fm.filter(year=year, is_derived=False, code="17").values_list("value", flat=True).first()
        return float(v) if v is not None else None

    ocf: Dict[int, Optional[float]] = {}
    for y in years:
        dep = depreciation(y) or 0.0
        wc_delta = ((d_inventories[y] or 0) + (d_receivables[y] or 0) - (d_payables[y] or 0)) if y in d_inventories else None
        if net_profit.get(y) is not None and wc_delta is not None:
            ocf[y] = net_profit[y] + dep - wc_delta
        else:
            ocf[y] = None

    # Net Cash Flow – pokud nemáme CFI/CFF, necháme None
    net_cash_flow = {y: None for y in years}

    return {
        "years": years,
        "revenue": revenue,
        "cogs": cogs,
        "overheads": overheads,
        "gross_margin": gross_margin,
        "gross_margin_pct": gross_margin_pct,
        "ebit": ebit,
        "net_profit": net_profit,
        "revenue_growth_pct": revenue_growth_pct,
        "cogs_growth_pct": cogs_growth_pct,
        "overheads_growth_pct": overheads_growth_pct,
        "operating_profit_pct": operating_profit_pct,
        "net_profit_pct": net_profit_pct,
        "cash_from_customers": cash_from_customers,
        "cash_to_suppliers": cash_to_suppliers,
        "gross_cash_profit": gross_cash_profit,
        "ocf": ocf,
        "net_cash_flow": net_cash_flow,
        "inventories": inventories,
        "receivables": receivables,
        "payables": payables,

        # 🔹 Přidáme „flattened“ listy pro grafy (přímo do šablony)
        "years_list": years,
        "revenue_list": [revenue[y] or 0 for y in years],
        "cogs_list": [cogs[y] or 0 for y in years],
        "overheads_list": [overheads[y] or 0 for y in years],
        "gross_margin_list": [gross_margin[y] or 0 for y in years],
        "ebit_list": [ebit[y] or 0 for y in years],
        "net_profit_list": [net_profit[y] or 0 for y in years],
        "cash_from_customers_list": [cash_from_customers[y] or 0 for y in years],
        "cash_to_suppliers_list": [cash_to_suppliers[y] or 0 for y in years],
        "gross_cash_profit_list": [gross_cash_profit[y] or 0 for y in years],
        "ocf_list": [ocf[y] or 0 for y in years],
        "net_cash_flow_list": [net_cash_flow[y] or 0 for y in years],
    }


# -----------------------------------------------------------------------------
# Původní dashboard – přehled + rozvaha dle roku
# -----------------------------------------------------------------------------
@login_required(login_url="/login/")
def dashboard(request):
    """
    Hlavní dashboard – vývoj vybraných metrik a rozvaha podle zvoleného roku.
    """
    docs = Document.objects.filter(owner=request.user).order_by("year")
    years = sorted({d.year for d in docs if d.year})

    # --- Vývoj (Revenue, EBIT, Net Profit) přes derived metriky
    tracked_income = ["revenue", "ebit", "net_profit"]
    income_series = {k: [] for k in tracked_income}

    for y in years:
        for key in tracked_income:
            val = FinancialMetric.objects.filter(
                document__owner=request.user,
                year=y,
                derived_key=key,
                is_derived=True,
            ).first()
            income_series[key].append(val.value if val else None)

    # --- Rozvaha podle zvoleného roku
    selected_year = request.GET.get("year")
    if selected_year and selected_year.isdigit():
        selected_year = int(selected_year)
    else:
        selected_year = years[-1] if years else None

    balance_assets, balance_liabilities = [], []
    if selected_year:
        metrics = (
            FinancialMetric.objects.filter(
                document__owner=request.user, year=selected_year, document__doc_type="balance", is_derived=False
            )
            .exclude(value__isnull=True)
        )

        for m in metrics:
            label = (m.label or "").lower()
            if "aktiv" in label:
                balance_assets.append({"label": m.label, "value": m.value})
            elif "pasiv" in label:
                balance_liabilities.append({"label": m.label, "value": m.value})

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


# -----------------------------------------------------------------------------
# Detail metrik / nahrané tabulky (ponecháno, jen drobná oprava "costs" → "cogs")
# -----------------------------------------------------------------------------
@login_required(login_url="/login/")
def metrics_dashboard(request):
    docs = Document.objects.filter(owner=request.user).order_by("-year")
    rows = ExtractedRow.objects.filter(table__document__owner=request.user)
    metrics = FinancialMetric.objects.filter(document__owner=request.user)

    revenue_by_year = {}
    costs_by_year = {}

    for m in metrics:
        if m.derived_key == "revenue":
            revenue_by_year[m.document.year] = m.value
        elif m.derived_key == "cogs":
            costs_by_year[m.document.year] = m.value

    context = {
        "documents": docs,
        "metrics": metrics,
        # připravíme čisté listy pro grafy
        "revenue_years": list(revenue_by_year.keys()),
        "revenue_values": list(revenue_by_year.values()),
        "costs_years": list(costs_by_year.keys()),
        "costs_values": list(costs_by_year.values()),
    }
    return render(request, "dashboard/metrics_dashboard.html", context)


# -----------------------------------------------------------------------------
# Profitability – nyní jen použije společný context
# -----------------------------------------------------------------------------
@login_required(login_url="/login/")
def profitability_dashboard(request):
    context = build_profitability_context(request)

    years = context.get("years", [])
    # převod dictů {year: val} -> list v pořadí years
    def as_list(d: dict) -> list:
        return [d.get(y) for y in years]

    context.update({
        "years_list": years,
        "revenue_list": as_list(context.get("revenue", {})),
        "cogs_list": as_list(context.get("cogs", {})),
        "overheads_list": as_list(context.get("overheads", {})),
        "gross_margin_list": as_list(context.get("gross_margin", {})),
        "gross_margin_pct_list": as_list(context.get("gross_margin_pct", {})),
        "ebit_list": as_list(context.get("ebit", {})),
        "net_profit_list": as_list(context.get("net_profit", {})),
        "revenue_growth_pct_list": as_list(context.get("revenue_growth_pct", {})),
        "cogs_growth_pct_list": as_list(context.get("cogs_growth_pct", {})),
        "overheads_growth_pct_list": as_list(context.get("overheads_growth_pct", {})),
        "operating_profit_pct_list": as_list(context.get("operating_profit_pct", {})),
        "net_profit_pct_list": as_list(context.get("net_profit_pct", {})),
        "cash_from_customers_list": as_list(context.get("cash_from_customers", {})),
        "cash_to_suppliers_list": as_list(context.get("cash_to_suppliers", {})),
        "gross_cash_profit_list": as_list(context.get("gross_cash_profit", {})),
        "ocf_list": as_list(context.get("ocf", {})),
    })

    # pokud nejsou žádná data
    if not years:
        return render(request, "dashboard/profitability.html", {"years_list": []})

    return render(request, "dashboard/profitability.html", context)

# -----------------------------------------------------------------------------
# Report view – stejný context, jiná šablona (tabulky + tlačítko exportu)
# -----------------------------------------------------------------------------
@login_required(login_url="/login/")
def report_view(request):
    context = build_profitability_context(request)
    return render(request, "dashboard/report.html", context)


# -----------------------------------------------------------------------------
# Export do PDF (Profit vs Cash tabulky)
# -----------------------------------------------------------------------------
@login_required(login_url="/login/")
def export_pdf(request):
    """
    Export Profit vs Cash tabulky do PDF (landscape).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20
    )

    styles = getSampleStyleSheet()
    elements: List = []

    elements.append(Paragraph("📊 Profit vs Cash Flow Report", styles["Heading1"]))
    elements.append(Spacer(1, 12))

    years = sorted(
        set(FinancialMetric.objects.filter(document__owner=request.user).values_list("year", flat=True))
    )
    if not years:
        elements.append(Paragraph("Žádná data nenalezena.", styles["Normal"]))
        doc.build(elements)
        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename="report.pdf")

    # Helper na hodnotu derived metriky
    def val(year: int, key: str) -> Optional[float]:
        fm = FinancialMetric.objects.filter(
            document__owner=request.user, year=year, derived_key=key, is_derived=True
        ).first()
        return fm.value if fm else None

    # Profit tabulka
    profit_rows = [
        ["Revenue"] + [val(y, "revenue") for y in years],
        ["COGS"] + [val(y, "cogs") for y in years],
        ["Gross Margin"] + [val(y, "gross_margin") for y in years],
        ["Overheads"] + [val(y, "overheads") for y in years],
        ["EBIT"] + [val(y, "ebit") for y in years],
        ["Net Profit"] + [val(y, "net_profit") for y in years],
    ]

    # Cash tabulka
    cash_rows = [
        ["Cash from Customers"] + [val(y, "cash_from_customers") for y in years],
        ["Cash to Suppliers"] + [val(y, "cash_to_suppliers") for y in years],
        ["Gross Cash Profit"] + [val(y, "gross_cash_profit") for y in years],
        ["Operating CF"] + [val(y, "ocf") for y in years],
        ["Net CF"] + [val(y, "net_cash_flow") for y in years],
    ]

    header = ["Metric"] + [str(y) for y in years]
    data = [header] + profit_rows + [[""]] + [header] + cash_rows

    table = Table(data, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4a90e2")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                # šedý oddělovač mezi Profit a Cash
                ("BACKGROUND", (0, len(profit_rows) + 1), (-1, len(profit_rows) + 1), colors.lightgrey),
            ]
        )
    )

    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename="profit_cash_report.pdf")
