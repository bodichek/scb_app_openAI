from __future__ import annotations

from typing import Any, Dict, List, Optional
import re
import unicodedata

import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

# PDF extrakce (fail-safe importy)
try:
    import camelot  # type: ignore
except Exception:
    camelot = None  # type: ignore

try:
    import pdfplumber  # type: ignore
except Exception:
    pdfplumber = None  # type: ignore

from .forms import MultiUploadForm
from .models import Document, ExtractedRow, ExtractedTable

# ==========================
# Utility
# ==========================

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")

def _normalize_header(name: Any) -> str:
    s = str(name if name is not None else "").strip().lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9 _\-.]", "", s)
    s = s.replace(" ", "_")
    return s or "col"

def _to_python_scalar(val: Any) -> Any:
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
    if hasattr(val, "item"):
        try:
            return val.item()
        except Exception:
            return str(val)
    if isinstance(val, (pd.Series, pd.DataFrame)):
        return str(val)
    return val

def _safe_is_number_str(s: str) -> bool:
    if not isinstance(s, str):
        return False
    s2 = s.replace("\u00A0", " ").replace(" ", "").replace(",", ".")
    return bool(_NUM_RE.fullmatch(s2))

def _to_float_if_number(val: Any) -> Optional[float]:
    v = _to_python_scalar(val)
    if v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            return float(v)
        except Exception:
            return None
    if isinstance(v, str) and _safe_is_number_str(v):
        try:
            return float(v.replace(" ", "").replace(",", "."))
        except Exception:
            return None
    return None

# ==========================
# Čištění DataFrame
# ==========================

def _clean_headers(df: pd.DataFrame) -> pd.DataFrame:
    try:
        if all(isinstance(c, int) for c in df.columns):
            header_idx: Optional[int] = None
            for i, row in df.iterrows():
                has_nonempty = any(str(x).strip() not in {"", "nan"} for x in row.tolist())
                if has_nonempty:
                    header_idx = i
                    break
            if header_idx is not None:
                new_cols = [str(x).strip() for x in df.iloc[header_idx].tolist()]
                df = df.iloc[header_idx + 1:].reset_index(drop=True)
                df.columns = new_cols
    except Exception:
        pass
    df.columns = [_normalize_header(c) for c in df.columns]
    return df

def _clean_cells(df: pd.DataFrame) -> pd.DataFrame:
    def _clean_val(v: Any) -> Any:
        try:
            if pd.isna(v):
                return None
        except Exception:
            pass
        s = str(v).strip()
        if s in {"", "nan", "-"}:
            return None
        s_compact = s.replace("\u00A0", " ").replace(" ", "").replace(",", ".")
        if _NUM_RE.fullmatch(s_compact):
            try:
                return float(s_compact)
            except Exception:
                pass
        return s
    return df.applymap(_clean_val)

def _drop_empty(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(axis=0, how="all")
    df = df.dropna(axis=1, how="all")
    return df.reset_index(drop=True)

def _df_to_rows(df: pd.DataFrame) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        row: Dict[str, Any] = {}
        for c in df.columns:
            row[str(c)] = _to_python_scalar(r[c])
        rows.append(row)
    return rows

# ==========================
# Heuristiky pro sloupce
# ==========================

_CODE_HDR_HINTS   = ("cislo_radku", "cislo", "radku", "radek", "c")
_LABEL_HDR_HINTS  = ("oznaceni", "ozna", "polozka", "poloz", "popis", "text", "nazev", "b")
_SKIP_VALUE_HDR   = ("korekce", "minule", "minuly", "predchozi")
_PREFER_VALUE_HDR = ("brutto", "stav", "netto", "bezne", "bezny", "current")

def _column_numeric_ratio(series: pd.Series) -> float:
    try:
        vals = series.dropna().astype(str)
    except Exception:
        return 0.0
    if len(vals) == 0:
        return 0.0
    isnum = vals.apply(_safe_is_number_str)
    return float(isnum.sum()) / float(len(vals))

def _find_code_col(df: pd.DataFrame) -> Optional[int]:
    for i, col in enumerate(df.columns):
        name = _normalize_header(col)
        if any(h in name for h in _CODE_HDR_HINTS):
            return i
    best_idx: Optional[int] = None
    best_score: float = 0.0
    for i in range(len(df.columns)):
        vals = df.iloc[:, i].dropna().astype(str).str.strip()
        if len(vals) == 0:
            continue
        short_digits = vals.apply(lambda s: s.isdigit() and len(s) <= 4)
        score = float(short_digits.sum()) / float(len(vals))
        if score > 0.6 and score > best_score:
            best_idx, best_score = i, score
    return best_idx

def _find_label_col(df: pd.DataFrame, code_idx: Optional[int]) -> Optional[int]:
    """Najdi textový sloupec s názvem položky (label). Preferuj hlavičky dle _LABEL_HDR_HINTS.
    Pokud nic nesedí, vrať None a použijeme fallback."""
    best_idx: Optional[int] = None
    best_pref: int = -1
    best_ratio: float = 1.0  # nižší = textovější

    for i, col in enumerate(df.columns):
        if code_idx is not None and i == code_idx:
            continue
        ser = df.iloc[:, i]
        # aspoň něco v tom sloupci musí být
        try:
            vals = ser.dropna().astype(str).str.strip()
        except Exception:
            continue
        if len(vals) == 0:
            continue

        # musí existovat nějaký nenumerický text
        any_text = any((v and not _safe_is_number_str(v)) for v in vals)
        if not any_text:
            continue

        name = _normalize_header(col)
        pref = 1 if any(h in name for h in _LABEL_HDR_HINTS) else 0
        ratio = _column_numeric_ratio(ser)

        if (pref > best_pref) or (pref == best_pref and ratio < best_ratio):
            best_idx, best_pref, best_ratio = i, pref, ratio

    return best_idx

def _find_value_col(df: pd.DataFrame, code_idx: Optional[int]) -> Optional[int]:
    cols = list(range(len(df.columns)))
    if code_idx is not None:
        cols = list(range(code_idx + 1, len(df.columns))) + list(range(0, code_idx + 1))

    best_idx: Optional[int] = None
    best_score: float = 0.0
    best_pref: int = -1

    for i in cols:
        if code_idx is not None and i == code_idx:
            continue  # ❗ nikdy nevybírej sloupec s kódem jako hodnotu
        name = str(df.columns[i])
        nname = _normalize_header(name)
        if any(k in nname for k in _SKIP_VALUE_HDR):
            continue
        ratio = _column_numeric_ratio(df.iloc[:, i])
        if ratio < 0.5:
            continue
        pref = 1 if any(k in nname for k in _PREFER_VALUE_HDR) else 0
        if (pref > best_pref) or (pref == best_pref and ratio > best_score):
            best_idx, best_score, best_pref = i, ratio, pref

    return best_idx

# ==========================
# Sekce (jen pro rozvahu)
# ==========================

def _norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.lower()

def _detect_section_from_row(row: Dict[str, Any]) -> Optional[str]:
    for v in row.values():
        v = _to_python_scalar(v)
        if isinstance(v, str):
            t = _norm_text(v)
            if "aktiva" in t:
                return "assets"
            if "pasiva" in t:
                return "liabilities"
    return None

def _normalize_code(raw: Any) -> Optional[str]:
    raw = _to_python_scalar(raw)
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    m = re.search(r"\d+", s)
    if not m:
        return None
    digits = m.group(0)
    if len(digits) == 1:
        digits = digits.zfill(2)
    return digits

# ==========================
# Zpracování PDF
# ==========================

def _process_document(pdf_file, user, year, doc_type: str, notes: Optional[str] = None) -> int:
    doc = Document.objects.create(
        file=pdf_file,
        original_filename=getattr(pdf_file, "name", "upload.pdf"),
        owner=user,
        doc_type=doc_type,
        year=year,
        notes=notes,
    )

    try:
        path = doc.file.path  # type: ignore[attr-defined]
    except Exception:
        return 0

    frames: List[pd.DataFrame] = []

    if camelot is not None:
        try:
            latt = camelot.read_pdf(path, flavor="lattice", pages="all")
            for i in range(getattr(latt, "n", 0)):
                frames.append(pd.DataFrame(latt[i].df))
        except Exception:
            pass
        try:
            stream = camelot.read_pdf(path, flavor="stream", pages="all")
            for i in range(getattr(stream, "n", 0)):
                frames.append(pd.DataFrame(stream[i].df))
        except Exception:
            pass

    if pdfplumber is not None:
        try:
            with pdfplumber.open(path) as pdf:
                for page in (pdf.pages or []):
                    for tb in (page.extract_tables() or []):
                        frames.append(pd.DataFrame(tb))
        except Exception:
            pass

    if not frames:
        return 0

    try:
        merged = pd.concat(frames, ignore_index=True)
    except Exception:
        return 0

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
        columns=[str(c) for c in merged.columns],
        meta={"rows": int(len(merged))},
    )

    code_idx  = _find_code_col(merged)
    value_idx = _find_value_col(merged, code_idx)
    label_idx = _find_label_col(merged, code_idx)

    current_section: Optional[str] = None

    for row in _df_to_rows(merged):
        # detekce sekce pouze u rozvahy
        if doc_type == "balance":
            sec_change = _detect_section_from_row(row)
            if sec_change:
                current_section = sec_change
                continue

        # kód
        code: Optional[str] = None
        if code_idx is not None:
            code = _normalize_code(row.get(str(merged.columns[code_idx])))
        if code is None:
            # fallback: první detekované číslo (ale krátké)
            for v in row.values():
                c = _normalize_code(v)
                if c:
                    code = c
                    break

        # label – nejdřív kolona label_idx, jinak první smysluplný text
        label: Optional[str] = None
        if label_idx is not None:
            cand = row.get(str(merged.columns[label_idx]))
            cand = _to_python_scalar(cand)
            if isinstance(cand, str) and cand.strip() and not _safe_is_number_str(cand):
                label = cand.strip()
        if label is None:
            for v in row.values():
                if isinstance(v, str) and v.strip() and not _safe_is_number_str(v):
                    label = v.strip()
                    break

        # hodnota – preferuj value_idx, jinak první číslo v řádku
        value: Optional[float] = None
        if value_idx is not None:
            value = _to_float_if_number(row.get(str(merged.columns[value_idx])))
        if value is None:
            for v in row.values():
                fv = _to_float_if_number(v)
                if fv is not None:
                    value = fv
                    break

        code  = _to_python_scalar(code)
        value = _to_python_scalar(value)
        safe_raw = {str(k): _to_python_scalar(v) for k, v in row.items()}

        if (code is not None) or (value is not None):
            ExtractedRow.objects.create(
                table=table,
                code=code,
                label=label,
                value=float(value) if isinstance(value, (int, float)) else None,
                section=current_section if doc_type == "balance" else None,
                raw_data=safe_raw,
            )

    return 1

# ==========================
# Views
# ==========================

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
        income_files  = form.cleaned_data.get("income_files")  or []

        if not balance_files and not income_files:
            messages.error(request, "Nebyl vybrán žádný soubor.")
            return render(request, "ingestion/upload.html", {"form": form})

        created_docs = 0
        saved_tables = 0

        for pdf in balance_files:
            created_docs += 1
            try:
                saved_tables += _process_document(pdf, request.user, year, "balance", notes)
            except Exception:
                pass

        for pdf in income_files:
            created_docs += 1
            try:
                saved_tables += _process_document(pdf, request.user, year, "income", notes)
            except Exception:
                pass

        if saved_tables > 0:
            messages.success(
                request,
                f"Nahráno {created_docs} souborů, uloženo {saved_tables} tabulek."
                if saved_tables != 1
                else f"Nahráno {created_docs} souborů, uložena 1 tabulka."
            )
        else:
            messages.warning(
                request,
                f"Nahráno {created_docs} souborů, ale nepodařilo se uložit žádnou tabulku."
            )
        return redirect("ingestion:documents")

    return render(request, "ingestion/upload.html", {"form": MultiUploadForm()})

@login_required(login_url="/login/")
def documents(request: HttpRequest) -> HttpResponse:
    docs = Document.objects.filter(owner=request.user).order_by("-uploaded_at")
    return render(request, "ingestion/documents.html", {"documents": docs})

@login_required(login_url="/login/")
def document_detail(request: HttpRequest, doc_id: int) -> HttpResponse:
    doc = get_object_or_404(Document, id=doc_id, owner=request.user)
    return render(request, "ingestion/document_detail.html", {"doc": doc})

@login_required(login_url="/login/")
def table_detail(request: HttpRequest, table_id: int) -> HttpResponse:
    table = get_object_or_404(ExtractedTable, id=table_id, document__owner=request.user)
    return render(request, "ingestion/table_detail.html", {"table": table})

@login_required(login_url="/login/")
@transaction.atomic
def delete_document(request: HttpRequest, doc_id: int) -> HttpResponse:
    doc = get_object_or_404(Document, id=doc_id, owner=request.user)
    if request.method == "POST":
        filename = doc.original_filename
        doc.delete()
        messages.success(request, f"Dokument {filename} byl smazán.")
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
