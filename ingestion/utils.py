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

def sum_codes(code_to_value: Dict[str, float], codes: List[str]) -> Optional[float]:
    vals = [code_to_value.get(c) for c in codes if c in code_to_value]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return float(sum(vals))
