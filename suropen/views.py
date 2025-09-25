from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.db import transaction
from .models import OpenAnswer

# OpenAI client
from openai import OpenAI
client = OpenAI()  # používá env OPENAI_API_KEY

# 🔹 Otázky napevno (sekce → otázky)
QUESTIONS = [
    {
        "section": "VÍCE ČASU",
        "items": [
            "Jak často a v jaké podobě se věnuji strategickému přemýšlení o směrování firmy?",
            "Co mi nejvíce bere čas a energii?",
            "V jaké roli se cítím nejvíce produktivní a užitečný/á?",
        ],
    },
    {
        "section": "VÍCE PENĚZ",
        "items": [
            "Mám dostatek finančních zdrojů na své potřeby a rozvoj firmy?",
            "Co jsou hlavní faktory ovlivňující růst mého byznysu?",
        ],
    },
    {
        "section": "MÉNĚ STRACHU",
        "items": [
            "Čeho se nejvíce obávám nebo mi brání v rozhodování?",
            "Kdyby všechny obavy a pochybnosti zmizely, co bych podniknul ve svém podnikání?",
            "Co mi nejvíce brání v mém podnikání?",
        ],
    },
]

def _build_ai_prompt(user_inputs):
    """
    user_inputs: list of dicts:
      {"section": "...", "question": "...", "answer": "..."}
    Vrátí messages pro OpenAI.
    """
    system = (
        "Jsi byznysový kouč. Stručně, konkrétně a akčně shrň odpovědi zakladatele firmy, "
        "identifikuj 3–5 hlavních zjištění a navrhni 5 krátkých, proveditelných doporučení. "
        "Používej češtinu, buď věcný, bez floskulí."
    )
    # poskládáme kompaktní vstup
    lines = []
    for i, r in enumerate(user_inputs, 1):
        lines.append(
            f"{i}) [{r['section']}] {r['question']}\n→ Odpověď: {r['answer']}"
        )
    user_text = (
        "Níže jsou moje otevřené odpovědi v kategoriích ČAS/PENÍZE/STRACH.\n\n" +
        "\n\n".join(lines) +
        "\n\nProsím: 1) krátké shrnutí, 2) klíčové překážky, 3) 5 konkrétních kroků na 14 dní."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text},
    ]

def _ask_openai(messages, model=None):
    model = model or getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            max_tokens=900,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        # graceful fallback
        return (
            "⚠️ Nepodařilo se získat odpověď od AI. Zkontroluj nastavení OPENAI_API_KEY/OPENAI_MODEL.\n"
            f"Detail: {type(e).__name__}: {e}"
        )

@login_required
def form(request):
    ai_text = None

    if request.method == "POST":
        # posbíráme vstupy
        collected = []
        # klíče formuláře: q-{section_index}-{question_index}
        for s_idx, block in enumerate(QUESTIONS):
            for q_idx, question in enumerate(block["items"]):
                key = f"q-{s_idx}-{q_idx}"
                ans = (request.POST.get(key) or "").strip()
                collected.append({
                    "section": block["section"],
                    "question": question,
                    "answer": ans,
                })

        # validace: aspoň něco musí být vyplněné
        any_text = any(item["answer"] for item in collected)
        if not any_text:
            return render(request, "suropen/form.html", {
                "questions": QUESTIONS,
                "error": "Vyplň prosím alespoň jednu odpověď.",
            })

        # AI
        messages = _build_ai_prompt(collected)
        ai_text = _ask_openai(messages)

        # Uložit do DB atomicky
        from uuid import uuid4
        batch_id = uuid4()
        with transaction.atomic():
            for item in collected:
                OpenAnswer.objects.create(
                    user=request.user,
                    batch_id=batch_id,
                    section=item["section"],
                    question=item["question"],
                    answer=item["answer"],
                    ai_response=ai_text,
                )

        # po POST zobrazíme form + AI výstup
        return render(request, "suropen/form.html", {
            "questions": QUESTIONS,
            "ai_text": ai_text,
            "just_submitted": True,
        })

    # GET
    return render(request, "suropen/form.html", {
        "questions": QUESTIONS,
    })

@login_required
def history(request):
    """
    Jednoduchý přehled vlastních předchozích odeslání seskupený dle batch_id.
    Žádná data jiných uživatelů se nikdy nezobrazí.
    """
    batches = (
        OpenAnswer.objects
        .filter(user=request.user)
        .order_by("-created_at")
        .values("batch_id", "created_at")
        .distinct()
    )

    # načteme položky pro každý batch (jen svoje)
    data = []
    for b in batches:
        items = list(
            OpenAnswer.objects.filter(user=request.user, batch_id=b["batch_id"])
            .order_by("created_at")
            .values("section", "question", "answer", "ai_response")
        )
        data.append({
            "batch_id": b["batch_id"],
            "created_at": b["created_at"],
            "items": items,
            "ai_response": items[0]["ai_response"] if items else None,
        })

    return render(request, "suropen/history.html", {"batches": data})
