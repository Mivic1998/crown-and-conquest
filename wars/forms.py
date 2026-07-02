from django import forms
from .models import War

class WarForm(forms.ModelForm):
    class Meta:
        model = War
        fields = [
            "attacker_rallying_cry"
        ]