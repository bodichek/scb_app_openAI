import pandas as pd

# Mapování čísla řádku na metriky
ROW_MAP = {
    "Revenue": [1, 2],          # Tržby
    "COGS": [4, 5],             # Náklady na prodané zboží + spotřeba
    "Overheads": [12, 13, 16, 17, 18],  # Režie
    "FinancialIncome": [20],
    "FinancialExpenses": [21],
    "IncomeTax": [40],
}

def extract_value(df, row_num):
    """Najde hodnotu podle čísla řádku ve sloupci slo_dku_c"""
    match = df[df["slo_dku_c"] == row_num]
    if not match.empty:
        try:
            return int(float(match.iloc[0, 3]))  # čtvrtý sloupec obsahuje hodnoty
        except Exception:
            return 0
    return 0

def calculate_metrics(tables_by_year):
    """
    Přijme {year: [ExtractedTable,...]}
    Vrátí {year: {"Revenue": .., "COGS": .., ...}}
    """
    metrics = {}
    for year, tables in tables_by_year.items():
        df = None
        # Vezmeme první tabulku z income
        for tb in tables:
            try:
                df = pd.DataFrame(list(tb.rows.values_list("data", flat=True)))
            except Exception:
                continue
        if df is None or df.empty:
            continue

        # výpočet metrik
        revenue = sum(extract_value(df, r) for r in ROW_MAP["Revenue"])
        cogs = sum(extract_value(df, r) for r in ROW_MAP["COGS"])
        gross_margin = revenue - cogs
        gross_margin_pct = (gross_margin / revenue * 100) if revenue else 0
        overheads = sum(extract_value(df, r) for r in ROW_MAP["Overheads"])
        operating_profit = gross_margin - overheads
        ebt = operating_profit + (extract_value(df, 20) - extract_value(df, 21))
        net_profit = ebt - extract_value(df, 40)

        metrics[year] = {
            "Revenue": revenue,
            "COGS": cogs,
            "Gross Margin": gross_margin,
            "Gross Margin %": gross_margin_pct,
            "Overheads": overheads,
            "Operating Profit": operating_profit,
            "Net Profit": net_profit,
        }
    return metrics


def calculate_growth(metrics_by_year):
    """
    Vypočítá meziroční růst metrik
    """
    years = sorted(metrics_by_year.keys())
    growth = {}
    for i in range(1, len(years)):
        y_prev = years[i-1]
        y_curr = years[i]
        prev, curr = metrics_by_year[y_prev], metrics_by_year[y_curr]
        growth[y_curr] = {
            "Revenue Growth %": ((curr["Revenue"] - prev["Revenue"]) / prev["Revenue"] * 100) if prev["Revenue"] else None,
            "COGS Growth %": ((curr["COGS"] - prev["COGS"]) / prev["COGS"] * 100) if prev["COGS"] else None,
            "Overheads Growth %": ((curr["Overheads"] - prev["Overheads"]) / prev["Overheads"] * 100) if prev["Overheads"] else None,
            "Operating Profit %": (curr["Operating Profit"] / curr["Revenue"] * 100) if curr["Revenue"] else None,
            "Net Profit %": (curr["Net Profit"] / curr["Revenue"] * 100) if curr["Revenue"] else None,
        }
    return growth
