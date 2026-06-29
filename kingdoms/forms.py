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

class CreateKingdomForm(forms.ModelForm):
    class Meta:
        model = Kingdom
        fields = ["name"]

from django import forms

from .models import Kingdom

class KingdomSettingsForm(forms.ModelForm):

    class Meta:
        model = Kingdom

        fields = [
            "name",
            "ruler_name",
        ]

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Kingdom Name",
                }
            ),

            "ruler_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ruler Name",
                }
            ),
        }

        labels = {
            "name": "Kingdom Name",
            "ruler_name": "Ruler Name",
        }