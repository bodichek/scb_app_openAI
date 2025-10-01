import json
import re
import openai
from django.conf import settings

# Definice metrik – fixní schéma pro appku
METRICS = {
    "Revenue": "Tržby",
    "GrossMargin": "Hrubá marže",
    "NetProfit": "Čistý zisk (po zdanění)",
    "Depreciation": "Odpisy a amortizace",
    "InterestPaid": "Zaplacené úroky",
    "IncomeTax": "Daň z příjmu",
    "ExtraordinaryItems": "Mimořádné výnosy/náklady",
    "DividendsPaid": "Vyplacené dividendy",
    "TotalAssets": "Aktiva celkem",
    "Cash": "Peněžní prostředky",
    "Receivables": "Pohledávky",
    "Inventory": "Zásoby",
    "CurrentAssets": "Oběžná aktiva",
    "FixedAssets": "Dlouhodobý hmotný majetek",
    "TotalLiabilities": "Celkové závazky",
    "TradePayables": "Závazky z obchodních vztahů",
    "ShortTermLiabilities": "Krátkodobé závazky",
    "ShortTermLoans": "Krátkodobé úvěry",
    "LongTermLoans": "Dlouhodobé úvěry"
}


def clean_number(value):
    """Ošetří čísla – převod na integer, podpora mínusů, fallback na 0."""
    if value in [None, "", "null", "None"]:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value)
    text = text.replace(" ", "").replace(",", "").replace("Kč", "")
    match = re.search(r"-?\d+", text)
    return int(match.group()) if match else 0


def build_prompt(table_text: str) -> str:
    metrics_list = "\n".join([f"- {k}: {v}" for k, v in METRICS.items()])
    return f"""
You are an expert in Czech financial statements.
Extract the following metrics from the table below.

Always return a valid JSON object with exactly these keys:
{list(METRICS.keys())}

Rules:
- Use integers only (no spaces, commas, or text).
- Negative values must be preserved.
- If the value is missing, return 0.

Mapping:
{metrics_list}

Table:
{table_text}
"""


def parse_financial_table(table_text: str) -> dict:
    """Pošle text tabulky do OpenAI a vrátí JSON s metrikami."""
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    prompt = build_prompt(table_text)

    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    raw_data = json.loads(response.choices[0].message.content)
    return {key: clean_number(raw_data.get(key)) for key in METRICS.keys()}
