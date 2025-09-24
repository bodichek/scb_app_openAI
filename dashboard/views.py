from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from ingestion.models import Document, ExtractedRow
import pandas as pd
import re

# 🔹 Aliasy pro rozpoznání řádků ve výkazech
ALIASES = {
    "revenue": ["tržby", "výnosy", "čistý obrat"],
    "costs": ["náklady", "spotřeba materiálu", "osobní náklady", "odpisy"],
    "profit": ["zisk", "výsledek hospodaření"],
    "assets": ["aktiva"],
    "liabilities": ["pasiva"],
    "equity": ["vlastní kapitál", "základní kapitál"],
}


def _rows_to_df(rows):
    """Převede queryset ExtractedRow na DataFrame."""
    if not rows.exists():
        return pd.DataFrame()
    data = [r.data for r in rows]
    return pd.DataFrame(data)


def _normalize_number(val):
    """Vyčistí číslo z textu."""
    if pd.isna(val):
        return None
    s = str(val).strip().replace(" ", "").replace("\u00a0", "")
    s = s.replace(",", ".")
    # odstraň tečky jako oddělovače tisíců (pokud nejsou desetinné)
    if re.match(r"^\d{1,3}(\.\d{3})*(,\d+)?$", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _find_value_in_row(row, columns):
    """Najde první smysluplnou hodnotu v řádku."""
    for col in columns[1:]:
        val = _normalize_number(row.get(col))
        if val is not None:
            return val
    return None


def _aggregate_income_statement(df):
    """Agregace výsledovky (výnosy, náklady, zisk)."""
    result = {"revenue": 0, "costs": 0, "profit": 0, "valid": True}

    if df.empty:
        return result

    for _, row in df.iterrows():
        text = str(row.get(df.columns[0], "")).lower()
        value = _find_value_in_row(row, df.columns)
        if value is None:
            continue

        if any(alias in text for alias in ALIASES["revenue"]):
            result["revenue"] += value
        elif any(alias in text for alias in ALIASES["costs"]):
            result["costs"] += value
        elif any(alias in text for alias in ALIASES["profit"]):
            result["profit"] += value

    # Validace: Výnosy - Náklady = Zisk
    if abs((result["revenue"] - result["costs"]) - result["profit"]) > 1e-3:
        result["valid"] = False

    return result


def _aggregate_balance_sheet(df):
    """Agregace rozvahy (aktiva, pasiva, VK)."""
    result = {"assets": 0, "liabilities": 0, "equity": 0, "valid": True}

    if df.empty:
        return result

    for _, row in df.iterrows():
        text = str(row.get(df.columns[0], "")).lower()
        value = _find_value_in_row(row, df.columns)
        if value is None:
            continue

        if any(alias in text for alias in ALIASES["assets"]):
            result["assets"] += value
        elif any(alias in text for alias in ALIASES["liabilities"]):
            result["liabilities"] += value
        elif any(alias in text for alias in ALIASES["equity"]):
            result["equity"] += value

    # Validace: Aktiva = Pasiva
    if abs(result["assets"] - result["liabilities"]) > 1e-3:
        result["valid"] = False

    return result


@login_required
def index(request):
    """Dashboard s agregovanými daty uživatele."""
    user_docs = Document.objects.filter(owner=request.user)

    income_statements = {}
    balance_sheets = {}

    for doc in user_docs:
        for table in doc.tables.all():
            rows = ExtractedRow.objects.filter(table=table)
            df = _rows_to_df(rows)
            if df.empty:
                continue

            year = doc.year or "Neznámý rok"

            if doc.doc_type == "income":
                agg = _aggregate_income_statement(df)
                if year not in income_statements:
                    income_statements[year] = agg
                else:
                    # přičteme, pokud už rok existuje
                    for k in ["revenue", "costs", "profit"]:
                        income_statements[year][k] += agg[k]
            elif doc.doc_type == "balance":
                agg = _aggregate_balance_sheet(df)
                if year not in balance_sheets:
                    balance_sheets[year] = agg
                else:
                    for k in ["assets", "liabilities", "equity"]:
                        balance_sheets[year][k] += agg[k]

    context = {
        "income_statements": income_statements,
        "balance_sheets": balance_sheets,
    }
    return render(request, "dashboard/index.html", context)
