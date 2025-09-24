import pandas as pd

def detect_row_code_column(df: pd.DataFrame) -> str | None:
    """Najde sloupec s číselnými kódy řádků (např. 1, 2, 3...)."""
    best_col, best_score = None, 0
    for col in df.columns:
        values = df[col].dropna().astype(str)
        score = sum(v.replace(".0", "").isdigit() for v in values)
        if score > best_score:
            best_score, best_col = score, col
    return best_col


def compute_metrics(df: pd.DataFrame) -> dict:
    """Spočítá základní metriky z tabulky výsledovky pro jeden rok."""
    code_col = detect_row_code_column(df)
    if not code_col:
        return {}

    mapping = {}
    for _, r in df.iterrows():
        try:
            code = str(r[code_col]).replace(".0", "")
            val = r.dropna().tolist()[-1]  # vezmeme poslední sloupec = běžné období
            if isinstance(val, str):
                val = float(val.replace(" ", "").replace(",", "."))
            mapping[code] = val
        except Exception:
            continue

    revenue = mapping.get("1", 0) + mapping.get("2", 0)
    cogs = mapping.get("4", 0) + mapping.get("5", 0)
    gross_margin = revenue - cogs
    gross_margin_pct = (gross_margin / revenue * 100) if revenue else 0

    overheads = (
        mapping.get("12", 0)
        + mapping.get("13", 0)
        + mapping.get("16", 0)
        + mapping.get("17", 0)
        + mapping.get("18", 0)
    )

    operating_profit = gross_margin - overheads
    ebt = operating_profit + (mapping.get("20", 0) - mapping.get("21", 0))
    net_profit = ebt - mapping.get("40", 0)

    return {
        "Revenue": revenue,
        "COGS": cogs,
        "Gross Margin": gross_margin,
        "Gross Margin %": gross_margin_pct,
        "Overheads": overheads,
        "Operating Profit": operating_profit,
        "Net Profit": net_profit,
    }


def compute_trends(metrics_by_year: dict[int, dict]) -> dict[int, dict]:
    """
    Spočítá meziroční růsty a % ukazatele.
    Input: {2021: {...}, 2022: {...}, ...}
    Output: {2022: {"Revenue Growth %": ..., "Net Profit %": ...}, ...}
    """
    trends = {}
    years = sorted(metrics_by_year.keys())
    for i, year in enumerate(years):
        m = metrics_by_year[year]
        trends[year] = {}

        # poměrové ukazatele
        trends[year]["Operating Profit %"] = (
            (m["Operating Profit"] / m["Revenue"] * 100) if m["Revenue"] else 0
        )
        trends[year]["Net Profit %"] = (
            (m["Net Profit"] / m["Revenue"] * 100) if m["Revenue"] else 0
        )

        # meziroční růsty
        if i > 0:
            prev = metrics_by_year[years[i - 1]]
            for key in ["Revenue", "COGS", "Overheads"]:
                prev_val, cur_val = prev.get(key, 0), m.get(key, 0)
                if prev_val:
                    growth = (cur_val - prev_val) / prev_val * 100
                else:
                    growth = 0
                trends[year][f"{key} Growth %"] = growth
    return trends
