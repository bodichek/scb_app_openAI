from django import forms

YEARS = [(str(y), str(y)) for y in range(2018, 2026)]


class MultiFileInput(forms.FileInput):
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        attrs = attrs or {}
        attrs["multiple"] = True
        super().__init__(attrs=attrs)


class MultiUploadForm(forms.Form):
    year = forms.ChoiceField(choices=YEARS, initial=YEARS[-1][0])
    balance_files = forms.FileField(widget=MultiFileInput(), required=False)
    income_files = forms.FileField(widget=MultiFileInput(), required=False)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
