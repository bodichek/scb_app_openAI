from django import forms


class MultipleFileInput(forms.ClearableFileInput):
    """
    Widget, který oficiálně povolí multiple výběr souborů.
    POZOR: nestačí dát attrs={"multiple": True} na FileInput – musí být allow_multiple_selected = True.
    """
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """
    FileField, který vrací LIST souborů (UploadedFile).
    Postará se o validaci každého souboru zvlášť.
    """
    widget = MultipleFileInput

    def __init__(self, *args, **kwargs):
        # zajistíme, že required=False nebude padat, když nic nepřijde
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        # žádné soubory a pole není povinné → vrať prázdný seznam
        if data in self.empty_values and not self.required:
            return []

        # pokud přišel jeden soubor, udělej z něj list
        if not isinstance(data, (list, tuple)):
            data = [data]

        cleaned_files = []
        errors = []

        for f in data:
            try:
                cleaned_files.append(super().clean(f, initial))
            except forms.ValidationError as e:
                errors.extend(e.error_list)

        if errors:
            raise forms.ValidationError(errors)

        return cleaned_files


class MultiUploadForm(forms.Form):
    year = forms.IntegerField(
        label="Rok",
        required=True,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    # ✅ Použijeme naše MultipleFileField – vrací LIST souborů
    balance_files = MultipleFileField(
        label="Soubory – Rozvaha",
        required=False,
    )

    income_files = MultipleFileField(
        label="Soubory – Výsledovka",
        required=False,
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
