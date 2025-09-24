from __future__ import annotations
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponse
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required
from .forms import MultiUploadForm
from .models import Document, ExtractedTable, ExtractedRow

import io
import re
import pandas as pd

# Extraction libraries
import camelot
import pdfplumber


def _clean_headers(df: pd.DataFrame) -> pd.DataFrame:
    # If columns look like 0..N, try to use the first non-empty row as header
    if all(isinstance(c, int) for c in df.columns):
        # find first row with at least one non-empty value
        header_idx = None
        for i, row in df.iterrows():
            if any((str(x).strip() != "" and str(x).strip().lower() != "nan") for x in row.tolist()):
                header_idx = i
                break
        if header_idx is not None:
            new_cols = [str(x).strip() for x in df.iloc[header_idx].tolist()]
            df = df.iloc[header_idx + 1 :].reset_index(drop=True)
            df.columns = new_cols

    def normalize(name: str) -> str:
        s = re.sub(r"\s+", " ", str(name or "").strip())
        s = s.lower()
        s = re.sub(r"[^a-z0-9 _-]", "", s)
        s = s.replace(" ", "_")
        return s or "col"

    df.columns = [normalize(c) for c in df.columns]
    return df


def _clean_cells(df: pd.DataFrame) -> pd.DataFrame:
    def clean_val(v):
        if pd.isna(v):
            return None
        s = str(v).strip()
        s = re.sub(r"\s+", " ", s)
        if s == "" or s.lower() == "nan":
            return None
        # normalize numbers
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
    df = df.reset_index(drop=True)
    return df


def _df_to_rows(df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for _, r in df.iterrows():
        row = {}
        for c in df.columns:
            row[str(c)] = r[c] if pd.notna(r[c]) else None
        rows.append(row)
    return rows


def _extract_with_camelot(path: str) -> list[dict]:
    tables = []
    try:
        # lattice first
        latt = camelot.read_pdf(path, flavor="lattice", pages="all")
        for i in range(latt.n):
            df = latt[i].df
            tables.append({"df": df, "method": "camelot-lattice", "page": latt[i].page})
    except Exception:
        pass

    try:
        # then stream
        stream = camelot.read_pdf(path, flavor="stream", pages="all")
        for i in range(stream.n):
            df = stream[i].df
            tables.append({"df": df, "method": "camelot-stream", "page": stream[i].page})
    except Exception:
        pass

    return tables


def _extract_with_pdfplumber(path: str) -> list[dict]:
    tables = []
    try:
        with pdfplumber.open(path) as pdf:
            for pageno, page in enumerate(pdf.pages, start=1):
                try:
                    tbs = page.extract_tables()
                    for idx, tb in enumerate(tbs):
                        df = pd.DataFrame(tb)
                        tables.append({"df": df, "method": "pdfplumber", "page": pageno})
                except Exception:
                    continue
    except Exception:
        pass
    return tables


@login_required
@transaction.atomic
def upload_pdf(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = MultiUploadForm(request.POST, request.FILES)
        if form.is_valid():
            year = int(form.cleaned_data["year"])
            notes = form.cleaned_data.get("notes")

            created_docs = []

            def handle_files(files, doc_type: str):
                nonlocal created_docs
                for f in files:
                    doc = Document.objects.create(
                        owner=request.user,
                        file=f,
                        original_filename=f.name,
                        notes=notes,
                        doc_type=doc_type,
                        year=year,
                    )
                    path = doc.file.path
                    candidates = _extract_with_camelot(path) or []
                    if not candidates:
                        candidates = _extract_with_pdfplumber(path) or []

                    for idx, item in enumerate(candidates):
                        raw_df = pd.DataFrame(item["df"]) if not isinstance(item["df"], pd.DataFrame) else item["df"]
                        df = raw_df.copy()
                        df = _clean_headers(df)
                        df = _clean_cells(df)
                        df = _drop_empty(df)

                        table = ExtractedTable.objects.create(
                            document=doc,
                            page_number=int(item.get("page") or 1),
                            table_index=idx,
                            method=item.get("method", "unknown"),
                            columns=[str(c) for c in df.columns],
                            meta={"source_rows": int(raw_df.shape[0]), "source_cols": int(raw_df.shape[1])},
                        )
                        rows = _df_to_rows(df)
                        ExtractedRow.objects.bulk_create(
                            [ExtractedRow(table=table, data=r) for r in rows]
                        )

                    created_docs.append(doc)

            balance_files = request.FILES.getlist("balance_files")
            income_files = request.FILES.getlist("income_files")

            if not balance_files and not income_files:
                messages.warning(request, "Nevybrali jste žádné soubory.")
                return redirect("ingestion:upload")

            if balance_files:
                handle_files(balance_files, Document.DocType.BALANCE)
            if income_files:
                handle_files(income_files, Document.DocType.INCOME)

            if len(created_docs) == 1:
                messages.success(request, "Soubor nahrán a tabulky extrahovány.")
                return redirect("ingestion:document_detail", doc_id=created_docs[0].id)
            else:
                messages.success(request, f"Nahráno a zpracováno {len(created_docs)} souborů.")
                return redirect("ingestion:documents")
        else:
            messages.error(request, "Neplatné hodnoty formuláře.")
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
