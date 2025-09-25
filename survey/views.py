from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Avg
from .models import Response, SurveySubmission



# 🔹 Otázky a odpovědi napevno
QUESTIONS = [
    {
        "category": "CEO",
        "question": "Mám dostatek času na strategická rozhodnutí a rozvoj firmy.",
        "labels": {
            "1-2": "Vůbec nemám čas na strategická rozhodnutí, jsem zahlcen operativou.",
            "3-4": "Mám velmi omezený čas na strategická rozhodnutí, většina mé práce je operativní.",
            "5-6": "Někdy mám čas na strategii, ale je to nepravidelné a omezené.",
            "7-8": "Mám pravidelně dostatek času věnovat se strategii firmy.",
            "9-10": "Věnuji se převážně strategickým rozhodnutím a rozvoji, operativa mě minimálně zatěžuje."
        }
    },
    {
        "category": "CEO",
        "question": "Práce v mojí firmě mě baví, naplňuje a inspiruje.",
        "labels": {
            "1-2": "Necítím žádnou motivaci nebo nadšení z práce ve firmě.",
            "3-4": "Práce mě baví, ale radost často ztrácím kvůli stresu nebo problémům.",
            "5-6": "Svou práci dělám rád, ale někdy se cítím přetížený.",
            "7-8": "Ze své práce mám většinou radost a těším se na ni.",
            "9-10": "Práce ve firmě mi dává smysl, baví mě a inspiruje k neustálému rozvoji sebe i firmy."
        }
    },
    {
        "category": "CEO",
        "question": "Firma mi poskytuje dostatečné zdroje.",
        "labels": {
            "1-2": "Nemám dostatek financí na své potřeby a škálování firmy.",
            "3-4": "Mám základní finanční příjmy, ale nedostačují na větší růst.",
            "5-6": "Mám dostatek zdrojů na provoz, ale omezený prostor pro investice.",
            "7-8": "Firma mi přináší tolik, kolik očekávám, a dokážu s tím růst.",
            "9-10": "Mám dostatečné financování a zdroje pro maximální rozvoj firmy."
        }
    },
    {
        "category": "LIDÉ",
        "question": "Leadership a osobní růst.",
        "labels": {
            "1-2": "Na rozvoj leadershipu a osobní růst svých lidí nemám čas ani zdroje.",
            "3-4": "Snažím se se svými lidmi stanovovat cíle a motivovat je, ale není to systematické.",
            "5-6": "Hledám svůj styl leadershipu a snažím se být srozumitelný pro ostatní.",
            "7-8": "Systematicky pracuji na svém osobním růstu a leadershipu.",
            "9-10": "Podporuji své lidi v jejich osobním růstu a rozvoji, leadership je na vysoké úrovni."
        }
    },
    {
        "category": "LIDÉ",
        "question": "Přitahování a získávání talentů.",
        "labels": {
            "1-2": "Naše firma má špatnou pověst, což ztěžuje nábor nových lidí.",
            "3-4": "Volné pozice obsazujeme pomalu nebo s problémy.",
            "5-6": "Volné pozice ve firmě se nám daří bez větších problémů obsazovat.",
            "7-8": "Ve firmě jsou správní lidé na správných místech, ale stále hledáme talenty.",
            "9-10": "Aktivně nás vyhledávají a oslovují talentovaní lidé."
        }
    },
    {
        "category": "LIDÉ",
        "question": "Management a firemní kultura.",
        "labels": {
            "1-2": "V naší firmě není jasná organizační struktura a pravidla.",
            "3-4": "Máme vytvořenou základní strukturu a rámcový popis odpovědností.",
            "5-6": "Máme jasnou strukturu, definované pozice a popisy práce.",
            "7-8": "Každá pozice má jasně stanovené odpovědnosti a funguje spolupráce.",
            "9-10": "Ve firmě je patrná kultura odpovědnosti na všech úrovních."
        }
    },
    {
        "category": "STRATEGIE",
        "question": "Identita firmy, její poslání a hodnoty.",
        "labels": {
            "1-2": "Ve firmě není povědomí o jejím poslání a hodnotách.",
            "3-4": "Poslání a hodnoty firmy jsou vnímané, ale ne příliš uplatňované.",
            "5-6": "Je popsáno poslání firmy a její klíčové hodnoty.",
            "7-8": "Poslání firmy a klíčové hodnoty jsou dobře známé a uplatňované v praxi.",
            "9-10": "Všichni členové týmu přirozeně žijí firemním posláním a hodnotami."
        }
    },
    {
        "category": "STRATEGIE",
        "question": "Vize a strategické odlišení.",
        "labels": {
            "1-2": "Firma nemá žádnou konkrétní vizi budoucího stavu.",
            "3-4": "Máme vizi budoucího stavu, ale nevíme, jakým způsobem ji dosáhnout.",
            "5-6": "Známe nejdůležitější strategické oblasti, ale potřebujeme je více rozpracovat.",
            "7-8": "Základy odlišující strategie máme, potřebujeme je více rozvíjet.",
            "9-10": "Máme zpracovanou jednoznačnou odlišující strategii, která nás posouvá vpřed."
        }
    },
    {
        "category": "OBCHOD",
        "question": "Znalost trhu a zákazníků.",
        "labels": {
            "1-2": "Nemáme žádné informace o trhu ani zákaznících.",
            "3-4": "Máme pouze základní představu o trhu a zákaznících.",
            "5-6": "Provádíme občasné analýzy trhu a zákazníků.",
            "7-8": "Pravidelně sledujeme trh a známe potřeby zákazníků.",
            "9-10": "Máme detailní znalosti trhu i zákazníků a využíváme je k růstu."
        }
    },
    {
        "category": "OBCHOD",
        "question": "Prodejní a marketingové procesy.",
        "labels": {
            "1-2": "Nemáme nastavené žádné procesy pro prodej a marketing.",
            "3-4": "Procesy pro prodej a marketing fungují jen velmi omezeně.",
            "5-6": "Máme základní procesy, ale nejsou systematické.",
            "7-8": "Procesy fungují a pravidelně je vyhodnocujeme.",
            "9-10": "Prodejní a marketingové procesy jsou na vysoké úrovni a přinášejí výsledky."
        }
    },
    {
        "category": "FINANCE",
        "question": "Finanční řízení a plánování.",
        "labels": {
            "1-2": "Nemáme přehled o financích a neplánujeme dopředu.",
            "3-4": "Finanční plánování děláme jen ad hoc.",
            "5-6": "Máme základní finanční řízení, ale není systematické.",
            "7-8": "Pravidelně plánujeme finance a sledujeme výsledky.",
            "9-10": "Máme profesionální finanční řízení a jasné finanční plány."
        }
    },
    {
        "category": "FINANCE",
        "question": "Zdroje financování.",
        "labels": {
            "1-2": "Nemáme přístup k žádným zdrojům financování.",
            "3-4": "Financování řešíme pouze ze základních zdrojů.",
            "5-6": "Občas využíváme externí zdroje, ale bez jasné strategie.",
            "7-8": "Máme dostupné různé zdroje financování a využíváme je dle potřeby.",
            "9-10": "Máme stabilní a diverzifikované zdroje financování."
        }
    },
    {
        "category": "PROCESY",
        "question": "Efektivita vnitřních procesů.",
        "labels": {
            "1-2": "Naše procesy jsou chaotické a neefektivní.",
            "3-4": "Procesy máme jen částečně popsané a nejsou důsledně dodržovány.",
            "5-6": "Procesy máme nastavené, ale vyžadují zlepšení.",
            "7-8": "Procesy jsou efektivní a většinou dobře fungují.",
            "9-10": "Naše procesy jsou vysoce efektivní a přinášejí konkurenční výhodu."
        }
    },
    {
        "category": "PROCESY",
        "question": "Digitalizace a technologie.",
        "labels": {
            "1-2": "Nemáme žádné digitální nástroje ani technologie.",
            "3-4": "Používáme jen základní digitální nástroje.",
            "5-6": "Postupně zavádíme digitální nástroje a technologie.",
            "7-8": "Máme většinu procesů digitalizovaných a využíváme moderní technologie.",
            "9-10": "Jsme technologicky vyspělá firma a inovace jsou součástí naší kultury."
        }
    },
    {
        "category": "VÝSLEDKY",
        "question": "Růst a ziskovost.",
        "labels": {
            "1-2": "Firma stagnuje a nedosahuje zisku.",
            "3-4": "Růst je minimální a zisk nízký.",
            "5-6": "Dosahujeme průměrného růstu a ziskovosti.",
            "7-8": "Firma stabilně roste a dosahuje dobré ziskovosti.",
            "9-10": "Firma dynamicky roste a má vysokou ziskovost."
        }
    },
    {
        "category": "VÝSLEDKY",
        "question": "Spokojenost zákazníků.",
        "labels": {
            "1-2": "Zákazníci jsou nespokojení a odcházejí.",
            "3-4": "Část zákazníků je spokojená, část odchází.",
            "5-6": "Většina zákazníků je spokojená, ale máme rezervy.",
            "7-8": "Zákazníci jsou převážně spokojení a zůstávají nám věrní.",
            "9-10": "Máme vysokou spokojenost zákazníků a ti nás aktivně doporučují."
        }
    }
]

@login_required
def questionnaire(request):
    if request.method == "POST":
        with transaction.atomic():
            submission = SurveySubmission.objects.create(user=request.user)
            for i, q in enumerate(QUESTIONS):
                score = int(request.POST.get(f"q{i}", 0))
                Response.objects.create(
                    user=request.user,
                    submission=submission,
                    question=q,
                    score=score,
                )
        return redirect("survey:detail", batch_id=submission.batch_id)

    return render(request, "survey/questionnaire.html", {"questions": QUESTIONS})


@login_required
def questionnaire(request):
    if request.method == "POST":
        with transaction.atomic():
            submission = SurveySubmission.objects.create(user=request.user)
            for i, q in enumerate(QUESTIONS):
                score = int(request.POST.get(f"q{i}", 0))
                Response.objects.create(
                    user=request.user,
                    submission=submission,
                    question=q["question"],  # uložíme jen text otázky
                    score=score,
                )
        return redirect("survey:detail", batch_id=submission.batch_id)

    return render(request, "survey/questionnaire.html", {"questions": QUESTIONS})


@login_required
def survey_summary(request):
    submissions = (
        SurveySubmission.objects.filter(user=request.user).order_by("-created_at")
    )
    return render(request, "survey/summary.html", {"submissions": submissions})


@login_required
def survey_detail(request, batch_id):
    submission = get_object_or_404(
        SurveySubmission, user=request.user, batch_id=batch_id
    )
    responses = submission.responses.all()
    avg_score = responses.aggregate(avg=Avg("score"))["avg"]

    return render(
        request,
        "survey/detail.html",
        {"submission": submission, "responses": responses, "avg_score": avg_score},
    )