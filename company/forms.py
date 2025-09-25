from django import forms
from .models import Company


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            "company_name",
            "respondent_name",
            "respondent_email",
            "phone",
            "about",
            "ico",
            "industry",
            "company_size",
            "coach",
        ]
        widgets = {
            "company_name": forms.TextInput(attrs={"class": "form-control"}),
            "respondent_name": forms.TextInput(attrs={"class": "form-control"}),
            "respondent_email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "about": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "ico": forms.TextInput(attrs={"class": "form-control"}),
            "industry": forms.TextInput(attrs={"class": "form-control"}),
            "company_size": forms.Select(attrs={"class": "form-select"}),
            "coach": forms.Select(attrs={"class": "form-select"}),
        }
