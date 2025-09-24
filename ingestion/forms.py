from django import forms


class UploadPDFForm(forms.Form):
    file = forms.FileField(allow_empty_file=False)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
