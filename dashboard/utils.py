from ingestion.models import ExtractedRow

# Výsledovka (doc_type='income')
ROW_MAP_INCOME = {
    "01": "Revenue",
    "03": "COGS",
    "09": "Overheads",
    "30": "Operating_Profit",
    "49": "Profit_Before_Tax",
    "53": "Net_Profit",
}

# Rozvaha (doc_type='balance')
ROW_MAP_BALANCE_ASSETS = {  # sekce = assets
    "01": "Assets_Total",
    "37": "Current_Assets",
    "75": "Cash",
}
ROW_MAP_BALANCE_LIAB = {    # sekce = liabilities
    "01": "Liabilities_Total",
    "02": "Equity",
    "21": "Profit_Current_Year",
}

def _value_for(rows, code: str, section: str | None = None) -> float:
    for r in rows:
        if (r.code or "").strip() == code and (section is None or r.section == section):
            if r.value is not None:
                return float(r.value)
    return 0.0

def calculate_metrics(user, year: int) -> dict:
    rows = ExtractedRow.objects.filter(
        table__document__owner=user,
        table__document__year=year
    ).select_related("table__document")

    metrics = {
        # income
        "Revenue": 0.0, "COGS": 0.0, "Overheads": 0.0,
        "Operating_Profit": 0.0, "Profit_Before_Tax": 0.0, "Net_Profit": 0.0,
        # balance
        "Assets_Total": 0.0, "Current_Assets": 0.0, "Cash": 0.0,
        "Liabilities_Total": 0.0, "Equity": 0.0, "Profit_Current_Year": 0.0,
        # derived
        "Gross_Margin": 0.0, "Gross_Margin_Pct": 0.0,
    }

    income_rows = [r for r in rows if r.table.document.doc_type == "income"]
    balance_rows = [r for r in rows if r.table.document.doc_type == "balance"]

    # Income
    for code, metric in ROW_MAP_INCOME.items():
        metrics[metric] = _value_for(income_rows, code)
    metrics["Gross_Margin"] = metrics["Revenue"] - metrics["COGS"]
    metrics["Gross_Margin_Pct"] = (metrics["Gross_Margin"] / metrics["Revenue"] * 100.0) if metrics["Revenue"] else 0.0
    if not metrics["Operating_Profit"]:
        metrics["Operating_Profit"] = metrics["Gross_Margin"] - metrics["Overheads"]

    # Balance
    for code, metric in ROW_MAP_BALANCE_ASSETS.items():
        metrics[metric] = _value_for(balance_rows, code, section="assets")
    for code, metric in ROW_MAP_BALANCE_LIAB.items():
        metrics[metric] = _value_for(balance_rows, code, section="liabilities")

    return metrics

def calculate_growth(metrics_by_year: dict[int, dict]) -> dict[int, dict]:
    years_sorted = sorted(metrics_by_year.keys())
    growth_by_year: dict[int, dict] = {}

    def growth(curr_val, prev_val):
        if prev_val:
            return ((curr_val - prev_val) / abs(prev_val)) * 100.0
        return 0.0

    for i in range(1, len(years_sorted)):
        y = years_sorted[i]
        p = years_sorted[i - 1]
        m, mp = metrics_by_year[y], metrics_by_year[p]
        growth_by_year[y] = {
            "Revenue_Growth":       growth(m["Revenue"],          mp["Revenue"]),
            "COGS_Growth":          growth(m["COGS"],             mp["COGS"]),
            "Overheads_Growth":     growth(m["Overheads"],        mp["Overheads"]),
            "Operating_Profit_Pct": growth(m["Operating_Profit"], mp["Operating_Profit"]),
            "Net_Profit_Pct":       growth(m["Net_Profit"],       mp["Net_Profit"]),
        }
    return growth_by_year
