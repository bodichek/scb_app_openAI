import pdfplumber
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from ingestion.models import Document, FinancialStatement
from ingestion.openai_parser import parse_financial_table


@login_required
def process_pdf(request, document_id):
    """Načte PDF, pošle tabulku do OpenAI a uloží výsledky."""
    document = get_object_or_404(Document, id=document_id, owner=request.user)

    with pdfplumber.open(document.file.path) as pdf:
        all_text = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())

    # parsování přes OpenAI
    data = parse_financial_table(all_text)

    # uložení výsledků pro konkrétní rok
    FinancialStatement.objects.update_or_create(
        owner=request.user,
        year=document.year,
        defaults={"document": document, "data": data}
    )

    return redirect("dashboard:index")
