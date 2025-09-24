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
    """Převede DataFrame na list řádků (dictů)."""
    rows: list[dict] = []
    for _, r in df.iterrows():
        row = {}
        for c in df.columns:
            val = r[c]
            # Pokud je to Series nebo list → vezmeme první hodnotu
            if isinstance(val, (pd.Series, list)):
                val = val[0] if len(val) > 0 else None
            if pd.isna(val):
                val = None
            row[str(c)] = val
        rows.append(row)
    return rows


# 🔹 Pomocná funkce pro zpracování jednoho dokumentu
def _process_document(pdf_file, user, year, doc_type, notes=None) -> int:
    """Uloží Document + tabulky + řádky, vrátí počet tabulek."""
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

    # Camelot lattice
    try:
        latt = camelot.read_pdf(path, flavor="lattice", pages="all")
        for i in range(latt.n):
            tables.append({"df": latt[i].df, "method": "camelot-lattice", "page": latt[i].page})
    except Exception:
        pass

    # Camelot stream
    try:
        stream = camelot.read_pdf(path, flavor="stream", pages="all")
        for i in range(stream.n):
            tables.append({"df": stream[i].df, "method": "camelot-stream", "page": stream[i].page})
    except Exception:
        pass

    # pdfplumber fallback
    try:
        with pdfplumber.open(path) as pdf:
            for pageno, page in enumerate(pdf.pages, start=1):
                for tb in page.extract_tables() or []:
                    tables.append({"df": pd.DataFrame(tb), "method": "pdfplumber", "page": pageno})
    except Exception:
        pass

    total = 0
    for idx, tb in enumerate(tables, start=1):
        df = pd.DataFrame(tb["df"])
        df = _clean_headers(df)
        df = _clean_cells(df)
        df = _drop_empty(df)
        if df.empty:
            continue

        table = ExtractedTable.objects.create(
            document=doc,
            page_number=tb["page"],
            table_index=idx,
            method=tb["method"],
            columns=list(df.columns),
            meta={"rows": len(df)}
        )

        for row in _df_to_rows(df):
            ExtractedRow.objects.create(table=table, data=row)

        total += 1

    return total


# 🔹 Views
@login_required
@transaction.atomic
def upload_pdf(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = MultiUploadForm(request.POST, request.FILES)
        if form.is_valid():
            year = form.cleaned_data.get("year")
            notes = form.cleaned_data.get("notes")

            balance_files = form.cleaned_data.get("balance_files", [])
            income_files = form.cleaned_data.get("income_files", [])

            created_docs = 0
            total_tables = 0

            for pdf_file in balance_files:
                created_docs += 1
                total_tables += _process_document(pdf_file, request.user, year, "balance", notes)

            for pdf_file in income_files:
                created_docs += 1
                total_tables += _process_document(pdf_file, request.user, year, "income", notes)

            messages.success(request, f"Nahráno {created_docs} souborů, extrahováno {total_tables} tabulek.")
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
