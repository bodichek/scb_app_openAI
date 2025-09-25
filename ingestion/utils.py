import pdfplumber
from .models import Document, ExtractedTable, ExtractedRow


def detect_code_column(rows, sample_size=10):
    """Najde sloupec, kde je nejvíc čísel typu 001, 002, …"""
    sample = rows[:sample_size]
    best_col, best_score = None, 0
    for col_idx in range(len(sample[0])):
        numeric_like = sum(
            1 for r in sample if str(r[col_idx]).strip().isdigit()
        )
        if numeric_like > best_score:
            best_score = numeric_like
            best_col = col_idx
    return best_col


def detect_value_column(rows, code_col, sample_size=10):
    """Najde první číselný sloupec vpravo od code (aktuální období)."""
    sample = rows[:sample_size]
    for col_idx in range(code_col + 1, len(sample[0])):
        numeric_like = 0
        for r in sample:
            val = str(r[col_idx]).replace(" ", "").replace(",", ".")
            if val.replace(".", "", 1).isdigit():
                numeric_like += 1
        if numeric_like >= len(sample) // 2:
            return col_idx
    return None


def normalize_row(row, code_col, value_col):
    """Vrátí normalizovaný řádek: code, value a raw_data."""
    code = str(row[code_col]).strip() if row[code_col] else None
    value = None
    if value_col is not None and value_col < len(row):
        try:
            value = float(str(row[value_col]).replace(",", ".").replace(" ", ""))
        except (ValueError, TypeError):
            pass
    return {"code": code, "value": value, "raw_data": row}


def process_table(rows, extracted_table):
    """Projede tabulku, detekuje sloupce a uloží řádky do DB."""
    if not rows:
        return

    code_col = detect_code_column(rows)
    value_col = detect_value_column(rows, code_col)

    for row in rows[1:]:  # přeskočíme hlavičku
        norm = normalize_row(row, code_col, value_col)
        if norm["code"] and norm["value"] is not None:
            ExtractedRow.objects.create(
                table=extracted_table,
                code=norm["code"],
                value=norm["value"],
                raw_data={f"col{i}": str(cell) for i, cell in enumerate(row)},
            )


def extract_pdf_tables(document: Document):
    """Hlavní funkce – načte PDF, projde tabulky a uloží je do DB."""
    with pdfplumber.open(document.file.path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for idx, tbl in enumerate(tables):
                extracted_table = ExtractedTable.objects.create(
                    document=document,
                    page_number=page.page_number,
                    table_index=idx,
                    method="pdfplumber",
                    columns=tbl[0] if tbl and tbl[0] else [],
                )
                process_table(tbl, extracted_table)
