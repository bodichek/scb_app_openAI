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
        "revenue": ["01", "02"],                  # Tržby vlastní výrobky/služby + Tržby zboží
        "cogs": ["04", "05"],                     # Náklady na prodané zboží + Výkonová spotřeba
        "overheads": ["12", "13", "16", "17", "18"],  # Osobní náklady, Daně a poplatky, Odpisy, Ostatní provozní náklady

        # 2) Podpůrné položky pro EBT / Net Profit
        "other_operating_income": ["15"],         # (neodečítáme v Overheads, vstupuje až do EBIT jen u varianty „z řádků“)
        "fin_income": ["20"],                     # Finanční výnosy
        "fin_expense": ["21"],                    # Finanční náklady
        "tax": ["40"],                            # Daň z příjmů
    },

    # Pro výpočet „cash“ indikátorů (používá už tvůj profitability_dashboard)
    "balance": {
        "inventories": ["055", "056", "057"],
        "receivables_trade": ["065", "066"],
        "payables_trade": ["105", "106"],
    },
}

# ---------------------------------------------------------------------
# Utility funkce
# ---------------------------------------------------------------------
def sum_codes(code_map: Dict[str, Optional[float]], codes: Iterable[str]) -> Optional[float]:
    acc = 0.0
    has_any = False
    for c in codes:
        v = code_map.get(c)
        if v is not None:
            acc += float(v)
            has_any = True
    return acc if has_any else None

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
    # základní bloky
    revenue   = sum_codes(code_map, income_map.get("revenue", []))
    cogs      = sum_codes(code_map, income_map.get("cogs", []))
    overheads = sum_codes(code_map, income_map.get("overheads", []))

    if revenue is not None:
        FinancialMetric.objects.create(document=document, year=year, owner=owner,
                                       derived_key="revenue", value=revenue, is_derived=True, label="Revenue")
    if cogs is not None:
        FinancialMetric.objects.create(document=document, year=year, owner=owner,
                                       derived_key="cogs", value=cogs, is_derived=True, label="COGS")
    if overheads is not None:
        FinancialMetric.objects.create(document=document, year=year, owner=owner,
                                       derived_key="overheads", value=overheads, is_derived=True, label="Overheads")

    # Gross margin & EBIT
    if revenue is not None and cogs is not None:
        gm = revenue - cogs
        FinancialMetric.objects.create(document=document, year=year, owner=owner,
                                       derived_key="gross_margin", value=gm, is_derived=True, label="Gross Margin")
        if overheads is not None:
            ebit = gm - overheads
            FinancialMetric.objects.create(document=document, year=year, owner=owner,
                                           derived_key="ebit", value=ebit, is_derived=True, label="EBIT")

    # Net Profit (pokud máš přímo řádek, nebo spočítáš přes fin_income/fin_expense/tax)
    fin_income = sum_codes(code_map, income_map.get("fin_income", []))
    fin_expense = sum_codes(code_map, income_map.get("fin_expense", []))
    tax = sum_codes(code_map, income_map.get("tax", []))

    if revenue is not None and cogs is not None:
        gm = revenue - cogs
        if overheads is not None:
            ebit = gm - overheads
            ebt = ebit + (fin_income or 0) - (fin_expense or 0)
            np = ebt - (tax or 0)
            FinancialMetric.objects.create(document=document, year=year, owner=owner,
                                           derived_key="net_profit", value=np, is_derived=True, label="Net Profit")
