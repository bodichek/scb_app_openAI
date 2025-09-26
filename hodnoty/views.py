from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
from ingestion.models import FinancialMetric


@login_required
@user_passes_test(lambda u: u.is_staff)
def values_list(request):
    # vezme všechny dopočítané metriky uživatele
    metrics = FinancialMetric.objects.filter(
        document__owner=request.user
    ).order_by("year", "label")

    # seskupíme podle roku
    years = {}
    for m in metrics:
        if m.year not in years:
            years[m.year] = {}
        years[m.year][m.label] = m.value

    return render(request, "hodnoty/list.html", {"years": years})
