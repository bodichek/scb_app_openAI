from __future__ import annotations
from typing import Any, Dict, List, Optional
import json

import pdfplumber
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from openai import OpenAI

from .forms import MultiUploadForm
from .models import Document, ExtractedTable, ExtractedRow, FinancialMetric
from .utils import DERIVED_FORMULAS, sum_codes

client = OpenAI(api_key=settings.OPENAI_API_KEY)

# -------------------------
# OpenAI + PDF
# -------------------------

def extract_text_from_pdf(path: str) -> str:
    parts: List[str] = []
    with pdfplumber.open(path) as pdf:
        for p in pdf.pages:
            parts.append(p.extract_text() or "")
    return "\n".join(parts)

def parse_pdf_with_gpt(pdf_path: str, doc_type: str) -> List[Dict[str, Any]]:
    """
    Pošle text PDF do GPT-4o mini a vrátí seznam řádků:
    {"code": "001", "label": "Tržby ...", "value": 123456.0}
    """
    text = extract_text_from_pdf(pdf_path)
    prompt = f"""
    From the following Czech financial statement text, extract a JSON array of rows.
    Each row MUST be an object with keys: "code" (string row number like "001" or "01"),
    "label" (string item name), "value" (float or null) for the CURRENT period.
    Return ONLY valid JSON. No explanations.

    Text:
    {text}
    """

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert in Czech financial statements. Output JSON only."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )

    try:
        data = json.loads(resp.choices[0].message.content)
        # očekáváme {"rows":[...]} nebo přímo [...]
        if isinstance(data, dict) and "rows" in data:
            rows = data["rows"]
        elif isinstance(data, list):
            rows = data
        else:
            rows = []
    except Exception:
        rows = []

    # sanitace
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        code = str(r.get("code") or "").strip()
        label = str(r.get("label") or "").strip()
        val = r.get("value")
        try:
            val = float(val) if val is not None else None
        except Exception:
            val = None
        if code or (val is not None):
            out.append({"code": code, "label": label, "value": val})
    return out

# -------------------------
# Normalizace + výpočty
# -------------------------

def rewrite_to_metrics(document: Document) -> None:
    """
    Přepíše ExtractedRow -> FinancialMetric (per kód).
    Nevyužíváme aliasy; klíčem je code.
    """
    # smažeme staré normalizované (aby se při přepisu roku neduplikovalo)
    FinancialMetric.objects.filter(document=document, is_derived=False).delete()

    rows = ExtractedRow.objects.filter(table__document=document)
    # Pozor: kód může být prázdný – ukládej jen ty, které code aspoň mají NEBO mají value
    bulk: List[FinancialMetric] = []
    for r in rows:
        if not (r.code or r.value is not None):
            continue
        bulk.append(FinancialMetric(
            document=document,
            code=(r.code or "").strip(),
            label=(r.label or "").strip(),
            value=r.value,
            year=document.year,
            is_derived=False,
            derived_key=""
        ))
    if bulk:
        FinancialMetric.objects.bulk_create(bulk, batch_size=100)

def calculate_and_store_derived(document: Document) -> None:
    """
    Dopočítané metriky (uloží se jako is_derived=True).
    Konfigurace je v DERIVED_FORMULAS (per doc_type).
    """
    FinancialMetric.objects.filter(document=document, is_derived=True).delete()

    # Mapa kód -> hodnota (poslední hodnota, když je více stejných kódů)
    code_map: Dict[str, float] = {}
    for m in FinancialMetric.objects.filter(document=document, is_derived=False):
        if m.code:
            code_map[m.code] = m.value if m.value is not None else code_map.get(m.code, None)

    formulas = DERIVED_FORMULAS.get(document.doc_type, {})
    derived_bulk: List[FinancialMetric] = []

    # jednoduché sumy dle mapy
    for key, codes in formulas.items():
        val = sum_codes(code_map, codes)
        derived_bulk.append(FinancialMetric(
            document=document,
            code="",
            label=f"Derived {key}",
            value=val,
            year=document.year,
            is_derived=True,
            derived_key=key
        ))

    # ukázkové složené metriky – pokud chceš, doplň si logiku nad derived_bulk (např. ebit = revenue - cogs - overheads)
    # zde příklad: pokud máme revenue a cogs/overheads, dopočítej hrubou marži a EBIT:
    def _find_val(key: str) -> Optional[float]:
        for x in derived_bulk:
            if x.derived_key == key:
                return x.value
        return None

    revenue = _find_val("revenue")
    cogs = _find_val("cogs")
    overheads = _find_val("overheads")

    gross_margin = (revenue - cogs) if (revenue is not None and cogs is not None) else None
    ebit = (gross_margin - overheads) if (gross_margin is not None and overheads is not None) else None

    derived_bulk.append(FinancialMetric(
        document=document, code="", label="Derived gross_margin", value=gross_margin,
        year=document.year, is_derived=True, derived_key="gross_margin"
    ))
    derived_bulk.append(FinancialMetric(
        document=document, code="", label="Derived ebit", value=ebit,
        year=document.year, is_derived=True, derived_key="ebit"
    ))

    if derived_bulk:
        FinancialMetric.objects.bulk_create(derived_bulk, batch_size=100)

# -------------------------
# Hlavní pipeline
# -------------------------

def _process_document(pdf_file, user, year, doc_type, notes=None) -> int:
    """
    1) Vytvoří Document
    2) Pošle PDF do OpenAI a uloží ExtractedTable + ExtractedRow
    3) Přepíše na FinancialMetric (per code)
    4) Dopočítá derived a uloží je
    """
    doc = Document.objects.create(
        file=pdf_file,
        original_filename=getattr(pdf_file, "name", "upload.pdf"),
        owner=user,
        doc_type=doc_type,
        year=year,
        notes=notes,
    )

    path = doc.file.path
    rows = parse_pdf_with_gpt(path, doc_type)

    if not rows:
        return 0

    table = ExtractedTable.objects.create(
        document=doc,
        page_number=1,
        table_index=1,
        method="gpt-4o-mini",
        columns=["code", "label", "value"],
        meta={"rows": len(rows)},
    )

    bulk_rows: List[ExtractedRow] = []
    for r in rows:
        bulk_rows.append(ExtractedRow(
            table=table,
            code=str(r.get("code") or "").strip(),
            label=str(r.get("label") or "").strip(),
            value=(float(r.get("value")) if r.get("value") is not None else None),
            section=None,
            raw_data=r
        ))
    if bulk_rows:
        ExtractedRow.objects.bulk_create(bulk_rows, batch_size=200)

    # Normalizace + výpočty
    rewrite_to_metrics(doc)
    calculate_and_store_derived(doc)

    return 1

# -------------------------
# Overwrite kontrola
# -------------------------

def _existing_doc(owner, year, doc_type) -> Optional[Document]:
    try:
        return Document.objects.filter(owner=owner, year=year, doc_type=doc_type).latest("uploaded_at")
    except Document.DoesNotExist:
        return None

# -------------------------
# Views
# -------------------------

@login_required(login_url="/login/")
@transaction.atomic
def upload_pdf(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = MultiUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "Formulář není validní.")
            return render(request, "ingestion/upload.html", {"form": form})

        year = form.cleaned_data.get("year")
        notes = form.cleaned_data.get("notes")
        balance_files = form.cleaned_data.get("balance_files") or []
        income_files = form.cleaned_data.get("income_files") or []

        if not balance_files and not income_files:
            messages.error(request, "Nebyl vybrán žádný soubor.")
            return render(request, "ingestion/upload.html", {"form": form})

        # Kontrola overwrite – pokud existuje doc pro rok+typ, zobrazíme potvrzení
        for doc_type, files in (("balance", balance_files), ("income", income_files)):
            if not files:
                continue
            exists = _existing_doc(request.user, year, doc_type)
            if exists and request.POST.get(f"confirm_overwrite_{doc_type}") != "yes":
                # zobraz potvrzení zvlášť pro každý typ, kde kolize nastala
                return render(request, "ingestion/confirm_overwrite.html", {
                    "form": form,
                    "year": year,
                    "doc_type": doc_type,
                    "existing_doc": exists,
                    "conf_name": f"confirm_overwrite_{doc_type}",
                    "message": f"Pro rok {year} a typ {doc_type} již existuje dokument: {exists.original_filename}. Přejete si ho přepsat?",
                })

        created_docs = 0
        saved_tables = 0

        for pdf in balance_files:
            created_docs += 1
            # pokud existuje starý a je potvrzeno přepsání, smažeme ho (včetně souboru) a jeho data
            old = _existing_doc(request.user, year, "balance")
            if old:
                old.delete()
            saved_tables += _process_document(pdf, request.user, year, "balance", notes)

        for pdf in income_files:
            created_docs += 1
            old = _existing_doc(request.user, year, "income")
            if old:
                old.delete()
            saved_tables += _process_document(pdf, request.user, year, "income", notes)

        if saved_tables > 0:
            messages.success(request, f"Nahráno {created_docs} souborů, uloženo {saved_tables} tabulek. Data byla normalizována a dopočtena.")
        else:
            messages.warning(request, f"Nahráno {created_docs} souborů, ale nepodařilo se uložit žádnou tabulku.")

        return redirect("ingestion:documents")

    # GET – seznam roků, kde už je něco nahráno (pro vizuální zvýraznění ve formuláři)
    existing_years = set(Document.objects.filter(owner=request.user).values_list("year", flat=True))
    form = MultiUploadForm()
    return render(request, "ingestion/upload.html", {"form": form, "existing_years": existing_years})

@login_required(login_url="/login/")
def documents(request: HttpRequest) -> HttpResponse:
    # zvýraznění: pro každou (year,doc_type) že existuje
    docs = Document.objects.filter(owner=request.user).order_by("-uploaded_at")
    years_map: Dict[int, Dict[str, bool]] = {}
    for d in docs:
        years_map.setdefault(d.year or 0, {}).setdefault(d.doc_type, True)
    return render(request, "ingestion/documents.html", {"documents": docs, "years_map": years_map})

@login_required(login_url="/login/")
def document_detail(request: HttpRequest, doc_id: int) -> HttpResponse:
    doc = get_object_or_404(Document, id=doc_id, owner=request.user)
    rows = ExtractedRow.objects.filter(table__document=doc).order_by("id")
    metrics_base = FinancialMetric.objects.filter(document=doc, is_derived=False).order_by("code")
    metrics_derived = FinancialMetric.objects.filter(document=doc, is_derived=True).order_by("derived_key")
    return render(request, "ingestion/document_detail.html", {
        "doc": doc,
        "rows": rows,
        "metrics_base": metrics_base,
        "metrics_derived": metrics_derived,
    })

@login_required(login_url="/login/")
def table_detail(request: HttpRequest, table_id: int) -> HttpResponse:
    table = get_object_or_404(ExtractedTable, id=table_id, document__owner=request.user)
    rows = table.rows.all().order_by("id")
    # graf: použijeme top N základních metrik podle hodnoty (bez derived)
    base_metrics = FinancialMetric.objects.filter(document=table.document, is_derived=False).exclude(value__isnull=True)
    base_metrics = base_metrics.order_by("-value")[:20]
    return render(request, "ingestion/table_detail.html", {"table": table, "rows": rows, "base_metrics": base_metrics})

@login_required(login_url="/login/")
@transaction.atomic
def delete_document(request: HttpRequest, doc_id: int) -> HttpResponse:
    doc = get_object_or_404(Document, id=doc_id, owner=request.user)
    if request.method == "POST":
        filename = doc.original_filename
        doc.delete()  # smaže i file z úložiště
        messages.success(request, f"Dokument {filename} byl smazán (včetně souboru v úložišti).")
        return redirect("ingestion:documents")
    return render(request, "ingestion/confirm_delete.html", {"object": doc, "type": "dokument"})

@login_required(login_url="/login/")
@transaction.atomic
def delete_table(request: HttpRequest, table_id: int) -> HttpResponse:
    table = get_object_or_404(ExtractedTable, id=table_id, document__owner=request.user)
    if request.method == "POST":
        doc_id = table.document.id
        table.delete()
        messages.success(request, "Tabulka byla smazána.")
        return redirect("ingestion:document_detail", doc_id=doc_id)
    return render(request, "ingestion/confirm_delete.html", {"object": table, "type": "tabulka"})
