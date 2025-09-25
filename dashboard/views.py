# dashboard/views.py
import io
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from ingestion.utils import DERIVED_FORMULAS, sum_codes
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

    # Výnosy podle roku (derived_key místo neexistujícího metric_key)
    revenue_by_year = {}
    for m in metrics:
        if m.derived_key == "revenue":
            revenue_by_year[m.document.year] = m.value

    # Náklady podle roku
    costs_by_year = {}
    for m in metrics:
        if m.derived_key == "costs":
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
    metrics = FinancialMetric.objects.filter(document__owner=request.user).order_by("year", "derived_key")
    y = 760
    p.setFont("Helvetica", 12)
    for m in metrics:
        label = m.label if getattr(m, "label", None) else (m.derived_key or m.code or "metric")
        p.drawString(100, y, f"{label} ({m.year}): {m.value}")
        y -= 20
        if y < 100:
            p.showPage()
            p.setFont("Helvetica", 12)
            y = 800

    p.showPage()
    p.save()
    buffer.seek(0)

    return FileResponse(buffer, as_attachment=True, filename="financial_metrics.pdf")

@login_required(login_url="/login/")
def profitability_dashboard(request):
    """
    Profitability Trends + Cash side podle zadané specifikace:
    - Revenue, COGS, Overheads
    - Gross Margin (abs), Gross Margin %
    - Operating Profit (EBIT) (varianta A z bloků)
    - Net Profit
    - Meziroční růsty: Revenue/COGS/Overheads Growth %
    - Cash: Cash from Customers, Cash to Suppliers, Gross Cash Profit, OCF, Net Cash Flow (indikativně)
    """
    # --- roky z výsledovek/rozvah
    income_docs = Document.objects.filter(owner=request.user, doc_type="income").order_by("year")
    balance_docs = Document.objects.filter(owner=request.user, doc_type="balance").order_by("year")

    years = sorted({d.year for d in income_docs if d.year})
    if not years:
        return render(request, "dashboard/profitability.html", {"years": [], "msg": "Nenalezeny výsledovky."})

    # --- načti odvozené (is_derived=True) i základní (is_derived=False) metriky
    fm = FinancialMetric.objects.filter(document__owner=request.user)

    # Helper: vezmi první hodnotu metriky dle derived_key v daném roce
    def get_derived(year: int, key: str) -> float | None:
        x = fm.filter(year=year, is_derived=True, derived_key=key).first()
        return x.value if x else None

    # Z raw kódů (pro fin_income, fin_expense, tax) si raději složíme hodnoty přímo (když by chyběl deriv.)
    def sum_raw_codes(year: int, codes: list[str]) -> float | None:
        vals = fm.filter(year=year, is_derived=False, code__in=codes).values_list("value", flat=True)
        nums = [float(v) for v in vals if v is not None]
        return sum(nums) if nums else None

    # --- 1) Základní bloky + výpočty
    revenue = {}
    cogs = {}
    overheads = {}
    gross_margin = {}
    gross_margin_pct = {}
    ebit = {}
    net_profit = {}

    for y in years:
        revenue[y]  = get_derived(y, "revenue")
        cogs[y]     = get_derived(y, "cogs")
        overheads[y]= get_derived(y, "overheads")

        gm = (revenue[y] - cogs[y]) if (revenue[y] is not None and cogs[y] is not None) else None
        gross_margin[y] = gm
        gross_margin_pct[y] = (gm / revenue[y] * 100.0) if (gm is not None and revenue[y]) else None

        # EBIT (varianta A): GM - Overheads
        ebit[y] = (gm - overheads[y]) if (gm is not None and overheads[y] is not None) else None

        # Net Profit = EBT - tax; EBT = EBIT + (fin_income - fin_expense)
        fin_income_codes = DERIVED_FORMULAS["income"].get("fin_income", [])
        fin_expense_codes = DERIVED_FORMULAS["income"].get("fin_expense", [])
        tax_codes = DERIVED_FORMULAS["income"].get("tax", [])

        fi  = sum_raw_codes(y, fin_income_codes) if fin_income_codes else None
        fe  = sum_raw_codes(y, fin_expense_codes) if fin_expense_codes else None
        tax = sum_raw_codes(y, tax_codes) if tax_codes else None

        ebt = (ebit[y] + (fi or 0) - (fe or 0)) if (ebit[y] is not None) else None
        net_profit[y] = (ebt - (tax or 0)) if (ebt is not None) else None

    # --- 2) Meziroční růsty
    def yoy_growth(series: dict[int, float | None]) -> dict[int, float | None]:
        out = {}
        for i, y in enumerate(years):
            if i == 0:
                out[y] = None
                continue
            prev = years[i-1]
            if series.get(prev) not in (None, 0) and series.get(y) is not None:
                out[y] = (series[y] - series[prev]) / series[prev] * 100.0
            else:
                out[y] = None
        return out

    revenue_growth_pct   = yoy_growth(revenue)
    cogs_growth_pct      = yoy_growth(cogs)
    overheads_growth_pct = yoy_growth(overheads)

    # --- 3) Profitability ratios
    operating_profit_pct = {y: (ebit[y] / revenue[y] * 100.0) if (ebit[y] is not None and revenue[y]) else None for y in years}
    net_profit_pct       = {y: (net_profit[y] / revenue[y] * 100.0) if (net_profit[y] is not None and revenue[y]) else None for y in years}

    # --- 4) Cash approximations (indikativně)
    # Potřebujeme Δ rozvahových položek: zásoby, pohledávky, závazky (trade)
    # 4.1 vytáhneme rozvahové řádky z ExtractedRow (sekce nebo fallback dle labelu)
    def bal_value(year: int, section: str | None, label_contains: str | None) -> float | None:
        qs = ExtractedRow.objects.filter(table__document__owner=request.user,
                                         table__document__doc_type="balance",
                                         table__document__year=year)
        if section:
            qs = qs.filter(section=section)
        if label_contains:
            qs = qs.filter(label__icontains=label_contains)
        vals = [r.value for r in qs if r.value is not None]
        return sum(vals) if vals else None

    # Preferenčně z DERIVED_FORMULAS['balance'] podle kódů:
    def bal_by_codes(year: int, codes: list[str]) -> float | None:
        vals = fm.filter(year=year, is_derived=False, code__in=codes, document__doc_type="balance").values_list("value", flat=True)
        nums = [float(v) for v in vals if v is not None]
        return sum(nums) if nums else None

    inv_codes = DERIVED_FORMULAS.get("balance", {}).get("inventories", [])
    rec_codes = DERIVED_FORMULAS.get("balance", {}).get("receivables_trade", [])
    pay_codes = DERIVED_FORMULAS.get("balance", {}).get("payables_trade", [])

    inventories = {}
    receivables = {}
    payables = {}

    for y in years:
        inv = bal_by_codes(y, inv_codes) if inv_codes else None
        rc  = bal_by_codes(y, rec_codes) if rec_codes else None
        py  = bal_by_codes(y, pay_codes) if pay_codes else None

        # fallback podle labelů, kdyby kódy neseděly
        inventories[y] = inv if inv is not None else bal_value(y, "asset", "zásob")
        receivables[y] = rc if rc is not None else bal_value(y, "asset", "pohledávk")
        payables[y]    = py if py is not None else bal_value(y, "liability", "závazk")

    # ΔX_t = X_t - X_{t-1}
    def delta(series: dict[int, float | None]) -> dict[int, float | None]:
        out = {}
        for i, y in enumerate(years):
            if i == 0:
                out[y] = None
                continue
            prev = years[i-1]
            if series.get(prev) is not None and series.get(y) is not None:
                out[y] = series[y] - series[prev]
            else:
                out[y] = None
        return out

    d_inventories = delta(inventories)
    d_receivables = delta(receivables)
    d_payables    = delta(payables)

    # Cash from Customers ≈ Revenue − ΔPohledávky
    cash_from_customers = {y: (revenue[y] - (d_receivables[y] or 0)) if revenue.get(y) is not None else None for y in years}

    # Cash to Suppliers ≈ COGS + ΔZásoby − ΔZávazky
    cash_to_suppliers   = {y: (cogs[y] + (d_inventories[y] or 0) - (d_payables[y] or 0)) if cogs.get(y) is not None else None for y in years}

    gross_cash_profit   = {y: (cash_from_customers[y] - cash_to_suppliers[y]) if (cash_from_customers.get(y) is not None and cash_to_suppliers.get(y) is not None) else None for y in years}

    # OCF ≈ Net Profit + Depreciation (ř.17) ± ΔWorking Capital (ΔZásoby + ΔPohledávky − ΔKrátkodobé závazky)
    # Použijeme Depreciation z raw kódu 17 (pokud ho najdeme v FM is_derived=False)
    def depreciation(year: int) -> float | None:
        v = fm.filter(year=year, is_derived=False, code="17").values_list("value", flat=True).first()
        return float(v) if v is not None else None

    ocf = {}
    for y in years:
        dep = depreciation(y) or 0.0
        wc_delta = ((d_inventories[y] or 0) + (d_receivables[y] or 0) - (d_payables[y] or 0)) if y in d_inventories else None
        if net_profit.get(y) is not None and wc_delta is not None:
            ocf[y] = net_profit[y] + dep - wc_delta
        else:
            ocf[y] = None

    # Net Cash Flow = OCF + CFI + CFF (nemáme-li CFI/CFF, necháme None)
    net_cash_flow = {y: None for y in years}

    context = {
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
    }
    return render(request, "dashboard/profitability.html", context)