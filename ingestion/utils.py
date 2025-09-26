from __future__ import annotations
from typing import Dict, List, Optional, Iterable
import unicodedata
from ingestion.models import ExtractedRow, FinancialMetric

# ---------------------------------------------------------------------
# Alias / normalizace textu (zatím nepoužíváme, kódujeme podle "code")
# ---------------------------------------------------------------------
ALIASES: Dict[str, List[str]] = {}

def normalize_text(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").strip().lower()

# ---------------------------------------------------------------------
# Mapování řádků na metriky
# ---------------------------------------------------------------------
DERIVED_FORMULAS = {
    "income": {
        # 1) Základní bloky
        "revenue": ["01", "02"],                      # Tržby vlastní výrobky/služby + Tržby zboží
        "cogs": ["04", "05"],                         # Náklady na prodané zboží + Výkonová spotřeba
        "overheads": ["12", "13", "16", "17", "18"],  # Osobní náklady, Daně a poplatky, Odpisy, Ostatní náklady

        # 2) Podpůrné položky pro EBT / Net Profit
        "other_operating_income": ["15"],             # Jiný provozní výnos
        "fin_income": ["20"],                         # Finanční výnosy
        "fin_expense": ["21"],                        # Finanční náklady
        "tax": ["40"],                                # Daň z příjmů
    },

    "balance": {
        "inventories": ["055", "056", "057"],
        "receivables_trade": ["065", "066"],
        "payables_trade": ["105", "106"],
    },
}

# ---------------------------------------------------------------------
# Utility funkce
# ---------------------------------------------------------------------
def sum_codes(code_map: Dict[str, Optional[float]], codes: Iterable[str]) -> float:
    """
    Bezpečně sečte hodnoty z code_map pro zadané kódy.
    Pokud některý kód chybí, bere se 0.0.
    Vždy vrací číslo (nikdy None).
    """
    acc = 0.0
    for c in codes:
        v = code_map.get(c)
        acc += float(v) if v is not None else 0.0
    return acc

def safe_div(numerator: float, denominator: float) -> float:
    """
    Bezpečné dělení – pokud je jmenovatel 0 nebo None, vrátí 0.
    """
    if not denominator:
        return 0.0
    return numerator / denominator

# ---------------------------------------------------------------------
# Uložení metrik (raw + derived) pro 1 dokument
# ---------------------------------------------------------------------
def save_financial_metrics(document):
    """
    Vezme raw ExtractedRow → uloží jako FinancialMetric(is_derived=False).
    Pak podle DERIVED_FORMULAS spočítá a uloží derived metriky (is_derived=True).
    """
    owner = document.owner
    year = document.year

    # 1) smaž staré metriky pro daný dokument
    FinancialMetric.objects.filter(document=document).delete()

    # 2) RAW metriky
    rows = ExtractedRow.objects.filter(table__document=document)
    code_map: Dict[str, Optional[float]] = {}
    for r in rows:
        code_map[r.code] = r.value
        FinancialMetric.objects.create(
            document=document,
            year=year,
            owner=owner,
            code=r.code,
            label=r.label,
            value=r.value,
            is_derived=False
        )

    # 3) Derived metriky z DERIVED_FORMULAS
    income_map = DERIVED_FORMULAS.get("income", {})

    revenue     = sum_codes(code_map, income_map.get("revenue", []))
    cogs        = sum_codes(code_map, income_map.get("cogs", []))
    overheads   = sum_codes(code_map, income_map.get("overheads", []))
    other_op    = sum_codes(code_map, income_map.get("other_operating_income", []))
    fin_income  = sum_codes(code_map, income_map.get("fin_income", []))
    fin_expense = sum_codes(code_map, income_map.get("fin_expense", []))
    tax         = sum_codes(code_map, income_map.get("tax", []))

    # --- základní bloky
    FinancialMetric.objects.create(document=document, year=year, owner=owner,
                                   derived_key="revenue", value=revenue, is_derived=True, label="Revenue")
    FinancialMetric.objects.create(document=document, year=year, owner=owner,
                                   derived_key="cogs", value=cogs, is_derived=True, label="COGS")
    FinancialMetric.objects.create(document=document, year=year, owner=owner,
                                   derived_key="overheads", value=overheads, is_derived=True, label="Overheads")

    # --- Gross Margin
    gross_margin = revenue - cogs
    FinancialMetric.objects.create(document=document, year=year, owner=owner,
                                   derived_key="gross_margin", value=gross_margin, is_derived=True, label="Gross Margin")

    # --- EBIT
    ebit = gross_margin - overheads + other_op
    FinancialMetric.objects.create(document=document, year=year, owner=owner,
                                   derived_key="ebit", value=ebit, is_derived=True, label="EBIT")

    # --- Profit before tax & Net Profit
    ebt = ebit + fin_income - fin_expense
    net_profit = ebt - tax
    FinancialMetric.objects.create(document=document, year=year, owner=owner,
                                   derived_key="net_profit", value=net_profit, is_derived=True, label="Net Profit")

    # --- Poměrové ukazatele
    gross_margin_pct = safe_div(gross_margin, revenue) * 100
    ebit_margin_pct  = safe_div(ebit, revenue) * 100
    net_profit_pct   = safe_div(net_profit, revenue) * 100

    FinancialMetric.objects.create(document=document, year=year, owner=owner,
                                   derived_key="gross_margin_pct", value=gross_margin_pct, is_derived=True, label="Gross Margin %")
    FinancialMetric.objects.create(document=document, year=year, owner=owner,
                                   derived_key="ebit_margin_pct", value=ebit_margin_pct, is_derived=True, label="EBIT Margin %")
    FinancialMetric.objects.create(document=document, year=year, owner=owner,
                                   derived_key="net_profit_pct", value=net_profit_pct, is_derived=True, label="Net Profit %")
