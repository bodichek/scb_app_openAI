from django.shortcuts import render, redirect
from .forms import CompanyForm


def company_identification(request):
    if request.method == "POST":
        form = CompanyForm(request.POST)
        if form.is_valid():
            company = form.save()
            return redirect("company:success")  # přesměrování na děkovací stránku
    else:
        form = CompanyForm()
    return render(request, "company/company_form.html", {"form": form})


def success(request):
    return render(request, "company/success.html")
