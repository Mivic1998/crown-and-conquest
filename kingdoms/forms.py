from django import forms
from .models import Kingdom

class PolicyForm(forms.ModelForm):
    class Meta:
        model = Kingdom
        fields = [
            "tax_rate",
            "agriculture_investment",
            "infrastructure_investment",
            "military_investment",
            "welfare_investment",
        ]