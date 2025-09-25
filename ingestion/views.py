# ingestion/views.py
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

client = OpenAI(api_key=getattr(settings, "OPENAI_API_KEY", None))

# -------------------------
# PDF text extraction
# -------------------------

def extract_text_from_pdf(path: str) -> str:
    """
    Otevře PDF pomocí pdfplumber a vrátí text všech stránek jako jeden string.
    """
    parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for p in pdf.pages:
            parts.append(p.extract_text() or "")
    return "\n".join(parts)

# -------------------------
# OpenAI parsing
# -------------------------

def parse_pdf_with_gpt(pdf_path: str, doc_type: str) -> List[Dict[str, Any]]:
    """
    Pošle text PDF do GPT a vrátí seznam řádků:
    {"code": "001", "label": "...", "value": 123456.0, "section": "asset/liability/other"}
    """
    text = extract_text_from_pdf(pdf_path)

    if doc_type == "balance":
        # Rozvaha = speciální prompt
        prompt = f"""
        From the following Czech BALANCE SHEET (rozvaha) text, extract a JSON array of rows.

        Each row MUST have these keys:
        - "code": string row number like "001" or "" if missing
        - "label": string item name
        - "value": float (use null if empty)
        - "section": one of ["asset", "liability"]

        Rules:
        - Rows related to Aktiva (assets) → section = "asset"
        - Rows related to Pasiva or Vlastní kapitál (liabilities/equity) → section = "liability"
        - Return ONLY valid JSON. No explanations.

        Text:
        {text}
        """
    else:
        # Výkaz zisku a ztráty = původní prompt
        prompt = f"""
        From the following Czech INCOME STATEMENT text, extract a JSON array of rows.
        Each row MUST be an object with keys:
        - "code": string row number like "001" or "01"
        - "label": string item name
        - "value": float or null for the CURRENT period
        Return ONLY valid JSON. No explanations.

        Text:
        {text}
        """

    resp = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are an expert in Czech accounting. Output JSON only."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )

    try:
        data = json.loads(resp.choices[0].message.content)
        if isinstance(data, dict) and "rows" in data:
            rows = data["rows"]
        elif isinstance(data, list):
            rows = data
        else:
            rows = []
    except Exception:
        rows = []

    # Sanitace
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        code = str(r.get("code") or "").strip()
        label = str(r.get("label") or "").strip()
        section = r.get("section") if doc_type == "balance" else None
        val = r.get("value")
        try:
            val = float(val) if val is not None else None
        except Exception:
            val = None
        if code or (val is not None):
            out.append({
                "code": code,
                "label": label,
                "value": val,
                "section": section
            })
    return out

# -------------------------
# Normalizace + výpočty
# -------------------------

def rewrite_to_metrics(document: Document) -> None:
    """Přepíše ExtractedRow -> FinancialMetric (per kód)."""
    FinancialMetric.objects.filter(document=document, is_derived=False).delete()

    rows = ExtractedRow.objects.filter(table__document=document)
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
    """Dopočítané metriky (uloží se jako is_derived=True)."""
    FinancialMetric.objects.filter(document=document, is_derived=True).delete()

    code_map: Dict[str, float] = {}
    for m in FinancialMetric.objects.filter(document=document, is_derived=False):
        if m.code:
            code_map[m.code] = m.value if m.value is not None else code_map.get(m.code, None)

    formulas = DERIVED_FORMULAS.get(document.doc_type, {})
    derived_bulk: List[FinancialMetric] = []

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
    """Pipeline: vytvoří Document -> GPT parsing -> ExtractedRow -> FinancialMetric -> Derived."""
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
            section=r.get("section") if "section" in r else None,
            raw_data=r
        ))
    if bulk_rows:
        ExtractedRow.objects.bulk_create(bulk_rows, batch_size=200)

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

        for doc_type, files in (("balance", balance_files), ("income", income_files)):
            if not files:
                continue
            exists = _existing_doc(request.user, year, doc_type)
            if exists and request.POST.get(f"confirm_overwrite_{doc_type}") != "yes":
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
            messages.success(request, f"Nahráno {created_docs} souborů, uloženo {saved_tables} tabulek.")
        else:
            messages.warning(request, f"Nahráno {created_docs} souborů, ale nepodařilo se uložit žádnou tabulku.")

        return redirect("ingestion:documents")

    existing_years = set(Document.objects.filter(owner=request.user).values_list("year", flat=True))
    form = MultiUploadForm()
    return render(request, "ingestion/upload.html", {"form": form, "existing_years": existing_years})

@login_required(login_url="/login/")
def documents_list(request: HttpRequest) -> HttpResponse:
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
    base_metrics = FinancialMetric.objects.filter(document=table.document, is_derived=False).exclude(value__isnull=True).order_by("-value")[:20]
    return render(request, "ingestion/table_detail.html", {"table": table, "rows": rows, "base_metrics": base_metrics})

@login_required(login_url="/login/")
@transaction.atomic
def delete_document(request: HttpRequest, doc_id: int) -> HttpResponse:
    doc = get_object_or_404(Document, id=doc_id, owner=request.user)
    if request.method == "POST":
        filename = doc.original_filename
        doc.delete()  # smaže i file z uložiště
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
