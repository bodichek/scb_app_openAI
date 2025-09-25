from django.shortcuts import render, redirect
from .forms import CompanyForm
from .models import Company



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

def company_list(request):
    companies = Company.objects.all()
    return render(request, "company/list.html", {"companies": companies})



def identification(request):
    return render(request, "company/identification.html")

def company_create(request):
    if request.method == "POST":
        form = CompanyForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("company:list")  # po uložení zpět na seznam
    else:
        form = CompanyForm()
    return render(request, "company/form.html", {"form": form})