from __future__ import annotations
from typing import Dict, List, Optional
import unicodedata

# ► V případě potřeby můžeš doplnit aliasy názvů (CZ/EN), ale NEPOUŽÍVÁME je – klíčem je code:
ALIASES: Dict[str, List[str]] = {
    # "001": ["dlouhodobý majetek", "non-current assets"],
    # "002": ["krátkodobý majetek", "current assets"],
    # ...
}

def normalize_text(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").strip().lower()

# ► Mapa dopočítaných metrik pro income/balance – zde nastavíš, z jakých kódů se počítají.
#   Můžeš rozdělit dle typů výkazů nebo variant formulářů (full/short).
DERIVED_FORMULAS: Dict[str, Dict[str, List[str]]] = {
    # Příklad pro výsledovku (income) – NASTAV SI DLE VLASTNÍCH ŘÁDKŮ:
    # revenue = součet kódů, které u vás reprezentují tržby/výnosy
    "income": {
        "revenue": ["001", "002"],     # např. 001 Tržby z prodeje výrobků a služeb, 002 Tržby za zboží
        "cogs":    ["003", "004"],     # spotřeba materiálu, prodané zboží
        "overheads": ["005","006","007"],  # služby, osobní náklady, odpisy...
        # Derived: gross_margin = revenue - cogs; ebit = gross_margin - overheads; net_profit = z konkrétního kódu
        # net_profit lze mapovat přímo, např. "net_profit": ["999"]
        "net_profit": ["999"],  # pokud máš řádek pro čistý zisk/ztrátu
    },
    # Příklad pro rozvahu (balance) – NASTAV SI:
    "balance": {
        # příklady:
        "total_assets": ["001","002","003"],   # aktiva celkem (pokud není přímo řádek „Aktiva celkem“)
        "total_equity": ["100","101","102"],   # vlastní kapitál...
        "total_liabilities": ["200","201"],    # cizí zdroje...
    }
}

def sum_codes(code_map: Dict[str, Optional[float]], codes: Iterable[str]) -> Optional[float]:
    acc = 0.0
    has_any = False
    for c in codes:
        v = code_map.get(c)
        if v is not None:
            acc += float(v)
            has_any = True
    return acc if has_any else None

# -----------------------------------------------------------------------------
# MAPOVÁNÍ: CZ výkaz → EN metriky v appce (na základě čísel řádků)
#
# Pozn.: Pokud máš jinou číselníkovou sadu, uprav zde bez zásahů do zbytku kódu.
# -----------------------------------------------------------------------------

DERIVED_FORMULAS = {
    # Výsledovka
    "income": {
        # 1) Základní bloky
        "revenue": ["01", "02"],            # Tržby vlastní výrobky/služby + Tržby zboží
        "cogs": ["04", "05"],               # Náklady na prodané zboží + Výkonová spotřeba
        "overheads": ["12", "13", "16", "17", "18"],  # Osobní náklady, Daně a poplatky, Odpisy, Ostatní provozní náklady

        # 2) Další podpůrné položky (pro EBT/Net Profit – nepřímo použijeme ve výpočtu)
        "other_operating_income": ["15"],   # Ostatní provozní výnosy (volitelně do EBIT „řádkovou“ variantou)
        "fin_income": ["20"],               # Finanční výnosy
        "fin_expense": ["21"],              # Finanční náklady
        "tax": ["40"],                      # Daň z příjmů
    },

    # Rozvaha – pro výpočty „cash“ indikátorů potřebujeme změny Stavů
    # Tady jsou "kanonická" čísla řádků – uprav podle své rozvahy:
    "balance": {
        "inventories": ["055", "056", "057"],      # Zásoby (součtově / nebo vyber přesně)
        "receivables_trade": ["065", "066"],       # Pohledávky z obchodního styku
        "payables_trade": ["105", "106"],          # Závazky z obchodního styku
        # můžeš přidat i další pracovní-kapitál položky (předplacené náklady, krátk. finanční majetek apod.)
    },
}