from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import CustomUserCreationForm
from financials.models import FinancialMetric


def home(request):
    # ✅ pokud uživatel je přihlášený, pošleme ho rovnou na dashboard
    if request.user.is_authenticated:
        return redirect("dashboard:index")
    return render(request, "home.html")


def signup(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data["email"]
            user.first_name = form.cleaned_data.get("first_name", "")
            user.last_name = form.cleaned_data.get("last_name", "")
            user.save()
            login(request, user)
            messages.success(request, "Účet byl úspěšně vytvořen 🎉")
            return redirect("dashboard:index")
        else:
            messages.error(request, "Opravit chyby ve formuláři.")
    else:
        form = CustomUserCreationForm()
    return render(request, "signup.html", {"form": form})
