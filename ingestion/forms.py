from django import forms


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiUploadForm(forms.Form):
    year = forms.IntegerField(
        label="Rok",
        required=True,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    balance_files = forms.FileField(
        label="Soubory – Rozvaha",
        required=False,
        widget=MultiFileInput(attrs={"multiple": True, "class": "form-control"}),
    )

    income_files = forms.FileField(
        label="Soubory – Výsledovka",
        required=False,
        widget=MultiFileInput(attrs={"multiple": True, "class": "form-control"}),
    )

    notes = forms.CharField(
        label="Poznámka",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def clean_year(self):
        year = self.cleaned_data.get("year")
        if year and (year < 1900 or year > 2100):
            raise forms.ValidationError("Zadejte rok mezi 1900 a 2100.")
        return year

    def clean(self):
        cleaned_data = super().clean()
        # validace necháme na views.py, protože používáme getlist()
        return cleaned_data
