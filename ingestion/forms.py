from django import forms

YEARS = [(y, str(y)) for y in range(2018, 2026)]

class MultiFileInput(forms.FileInput):
    allow_multiple_selected = True


class MultiUploadForm(forms.Form):
    year = forms.ChoiceField(choices=YEARS)
    statement_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    balance_files = forms.FileField(widget=MultiFileInput(attrs={"multiple": True}), required=False)
    income_files = forms.FileField(widget=MultiFileInput(attrs={"multiple": True}), required=False)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
