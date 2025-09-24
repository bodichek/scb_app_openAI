from django import forms

# Nabídka let (2018–2025)
YEARS = [(str(y), str(y)) for y in range(2018, 2026)]


class MultiFileInput(forms.ClearableFileInput):
    """Widget pro výběr více souborů."""
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        attrs = attrs or {}
        attrs["multiple"] = True
        super().__init__(attrs=attrs)

    def value_from_datadict(self, data, files, name):
        if not files:
            return []
        return files.getlist(name)


class MultiFileField(forms.FileField):
    """Form field pro více souborů najednou."""
    def clean(self, data, initial=None):
        if not data:
            if self.required:
                raise forms.ValidationError(
                    self.error_messages["required"], code="required"
                )
            return []

        if not isinstance(data, (list, tuple)):
            data = [data]

        cleaned = []
        errors = []
        for item in data:
            try:
                cleaned.append(super().clean(item, None))
            except forms.ValidationError as exc:
                errors.extend(exc.error_list)

        if errors:
            raise forms.ValidationError(errors)

        return cleaned


class MultiUploadForm(forms.Form):
    """Formulář pro nahrání více PDF – Rozvahy a Výsledovky."""
    year = forms.ChoiceField(
        choices=YEARS,
        initial=YEARS[-1][0],
        label="Rok"
    )
    balance_files = MultiFileField(
        widget=MultiFileInput(),
        required=False,
        label="Soubory – Rozvaha"
    )
    income_files = MultiFileField(
        widget=MultiFileInput(),
        required=False,
        label="Soubory – Výsledovka"
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
        label="Poznámka"
    )
