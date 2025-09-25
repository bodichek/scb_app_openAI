from django.shortcuts import redirect, render
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm


def home(request):
    # přihlášeného pošli rovnou na dashboard
    if request.user.is_authenticated:
        return redirect("dashboard:index")  # ✅ sjednoceno
    return render(request, "home.html")


def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)  # vestavěný formulář
        if form.is_valid():
            user = form.save(commit=False)
            # volitelně doplnitelné údaje
            user.email = form.cleaned_data.get("email", "")
            user.first_name = form.cleaned_data.get("first_name", "")
            user.last_name = form.cleaned_data.get("last_name", "")
            user.save()
            login(request, user)
            messages.success(request, "Účet byl úspěšně vytvořen 🎉")
            return redirect("dashboard:index")  # ✅ sjednoceno
        messages.error(request, "Oprav prosím chyby ve formuláři.")
    else:
        form = UserCreationForm()
    return render(request, "signup.html", {"form": form})


def signup_view(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # rovnou přihlásíme
            return redirect("dashboard:index")  # ✅ sjednoceno
    else:
        form = UserCreationForm()
    return render(request, "signup.html", {"form": form})
