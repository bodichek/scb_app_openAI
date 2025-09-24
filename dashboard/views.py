from __future__ import annotations
from django.shortcuts import render
from ingestion.models import ExtractedTable, ExtractedRow
from django.db.models import Count


def index(request):
    # Collect all known columns across tables
    known_columns = set()
    for t in ExtractedTable.objects.all():
        for c in t.columns:
            known_columns.add(c)
    known_columns = sorted(list(known_columns))

    group_by = request.GET.get("group_by")
    value_col = request.GET.get("value_col")
    agg = request.GET.get("agg", "count")

    chart = None
    if group_by and group_by in known_columns:
        # simple aggregation in Python: group-by over JSON rows in memory
        # For large data, migrate to Postgres JSONB and aggregate in SQL.
        data = []
        rows = ExtractedRow.objects.all().values_list("data", flat=True)
        for r in rows:
            key = r.get(group_by)
            if key is None:
                continue
            data.append(r)
        # aggregate
        from collections import defaultdict

        groups = defaultdict(list)
        for r in data:
            key = r.get(group_by)
            groups[key].append(r)

        labels = []
        values = []
        if agg == "sum" and value_col:
            for k, items in groups.items():
                s = 0.0
                for it in items:
                    v = it.get(value_col)
                    if isinstance(v, (int, float)):
                        s += float(v)
                labels.append(str(k))
                values.append(s)
        elif agg == "avg" and value_col:
            for k, items in groups.items():
                nums = [float(it.get(value_col)) for it in items if isinstance(it.get(value_col), (int, float))]
                labels.append(str(k))
                values.append(sum(nums) / len(nums) if nums else 0.0)
        else:  # count
            for k, items in groups.items():
                labels.append(str(k))
                values.append(len(items))

        chart = {
            "labels": labels,
            "values": values,
            "title": f"{agg.upper()} by {group_by}" if not value_col else f"{agg.upper()} {value_col} by {group_by}",
        }

    return render(
        request,
        "dashboard/index.html",
        {
            "known_columns": known_columns,
            "group_by": group_by,
            "value_col": value_col,
            "agg": agg,
            "chart": chart,
        },
    )

def dashboard_view(request):
    # tady můžeš později poslat data do šablony
    return render(request, "dashboard.html")