from __future__ import annotations
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponse
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required
from .forms import MultiUploadForm
from .models import Document, ExtractedTable, ExtractedRow

import pandas as pd
import re
import camelot
import pdfplumber

@login_required
@transaction.atomic
def upload_pdf(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        print("DEBUG POST keys:", request.POST.keys())
        print("DEBUG FILES keys:", request.FILES.keys())
        print("DEBUG FILES dict:", request.FILES)

        form = MultiUploadForm(request.POST, request.FILES)
# 🔹 Utility pro čištění tabulek
def _clean_headers(df: pd.DataFrame) -> pd.DataFrame:
    if all(isinstance(c, int) for c in df.columns):
        header_idx = None
        for i, row in df.iterrows():
            if any((str(x).strip() not in ["", "nan"]) for x in row.tolist()):
                header_idx = i
                break
        if header_idx is not None:
            new_cols = [str(x).strip() for x in df.iloc[header_idx].tolist()]
            df = df.iloc[header_idx + 1:].reset_index(drop=True)
            df.columns = new_cols

    def normalize(name: str) -> str:
        s = re.sub(r"\s+", " ", str(name or "").strip()).lower()
        s = re.sub(r"[^a-z0-9 _-]", "", s)
        return s.replace(" ", "_") or "col"

    df.columns = [normalize(c) for c in df.columns]
    return df


def _clean_cells(df: pd.DataFrame) -> pd.DataFrame:
    def clean_val(v):
        if pd.isna(v):
            return None
        s = str(v).strip()
        s = re.sub(r"\s+", " ", s)
        if s in ["", "nan"]:
            return None
        sn = s.replace(",", "")
        if re.fullmatch(r"-?\d+(\.\d+)?", sn):
            try:
                return float(sn)
            except Exception:
                pass
        return s
    return df.applymap(clean_val)


def _drop_empty(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(axis=0, how="all")
    df = df.dropna(axis=1, how="all")
    return df.reset_index(drop=True)


def _df_to_rows(df: pd.DataFrame) -> list[dict]:
    """Převede DataFrame na list řádků (dictů), čísla na int."""
    rows: list[dict] = []
    for _, r in df.iterrows():
        row = {}
        for c in df.columns:
            val = r[c]
            if pd.isna(val):
                val = None
            else:
                try:
                    num = float(val)
                    val = int(round(num))
                except Exception:
                    pass
            row[str(c)] = val
        rows.append(row)
    return rows


def _process_document(pdf_file, user, year, doc_type, notes=None) -> int:
    """Uloží Document + 1 spojenou tabulku + řádky, vrátí počet tabulek (vždy 1 nebo 0)."""
    doc = Document.objects.create(
        file=pdf_file,
        original_filename=pdf_file.name,
        owner=user,
        doc_type=doc_type,
        year=year,
        notes=notes
    )

    path = doc.file.path
    tables = []

    try:
        latt = camelot.read_pdf(path, flavor="lattice", pages="all")
        for i in range(latt.n):
            tables.append(pd.DataFrame(latt[i].df))
    except Exception:
        pass

    try:
        stream = camelot.read_pdf(path, flavor="stream", pages="all")
        for i in range(stream.n):
            tables.append(pd.DataFrame(stream[i].df))
    except Exception:
        pass

    try:
        with pdfplumber.open(path) as pdf:
            for pageno, page in enumerate(pdf.pages, start=1):
                for tb in page.extract_tables() or []:
                    tables.append(pd.DataFrame(tb))
    except Exception:
        pass

    if not tables:
        return 0

    merged = pd.concat(tables, ignore_index=True)
    merged = _clean_headers(merged)
    merged = _clean_cells(merged)
    merged = _drop_empty(merged)
    if merged.empty:
        return 0

    table = ExtractedTable.objects.create(
        document=doc,
        page_number=1,
        table_index=1,
        method="merged",
        columns=list(merged.columns),
        meta={"rows": len(merged)}
    )

    for row in _df_to_rows(merged):
        code = str(row.get("code") or row.get("číslo_řádku") or "")
        value = None
        for k, v in row.items():
            if isinstance(v, (int, float)):
                value = v
                break
        ExtractedRow.objects.create(table=table, code=code, value=value, raw_data=row)

    return 1


@login_required
@transaction.atomic
def upload_pdf(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = MultiUploadForm(request.POST, request.FILES)
        if form.is_valid():
            year = form.cleaned_data.get("year")
            notes = form.cleaned_data.get("notes")

            # ⚡ čtení souborů z request.FILES.getlist
            balance_files = request.FILES.getlist("balance_files")
            income_files = request.FILES.getlist("income_files")

            created_docs = 0
            total_tables = 0

            for pdf_file in balance_files:
                created_docs += 1
                total_tables += _process_document(pdf_file, request.user, year, "balance", notes)

            for pdf_file in income_files:
                created_docs += 1
                total_tables += _process_document(pdf_file, request.user, year, "income", notes)

            messages.success(request, f"Nahráno {created_docs} souborů, uložena {total_tables} tabulka.")
            return redirect("ingestion:documents")
    else:
        form = MultiUploadForm()

    return render(request, "ingestion/upload.html", {"form": form})


@login_required
def documents(request: HttpRequest) -> HttpResponse:
    docs = Document.objects.filter(owner=request.user).order_by("-uploaded_at")
    return render(request, "ingestion/documents.html", {"documents": docs})


@login_required
def document_detail(request: HttpRequest, doc_id: int) -> HttpResponse:
    doc = get_object_or_404(Document, id=doc_id, owner=request.user)
    return render(request, "ingestion/document_detail.html", {"doc": doc})


@login_required
def table_detail(request: HttpRequest, table_id: int) -> HttpResponse:
    table = get_object_or_404(ExtractedTable, id=table_id, document__owner=request.user)
    return render(request, "ingestion/table_detail.html", {"table": table})


@login_required
@transaction.atomic
def delete_document(request, doc_id):
    doc = get_object_or_404(Document, id=doc_id, owner=request.user)
    if request.method == "POST":
        filename = doc.original_filename
        doc.delete()
        messages.success(request, f"Dokument {filename} byl smazán.")
        return redirect("ingestion:documents")
    return render(request, "ingestion/confirm_delete.html", {"object": doc, "type": "dokument"})


@login_required
@transaction.atomic
def delete_table(request, table_id):
    table = get_object_or_404(ExtractedTable, id=table_id, document__owner=request.user)
    if request.method == "POST":
        table.delete()
        messages.success(request, "Tabulka byla smazána.")
        return redirect("ingestion:document_detail", doc_id=table.document.id)
    return render(request, "ingestion/confirm_delete.html", {"object": table, "type": "tabulka"})
