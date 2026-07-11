from django import forms
from .models import War

class WarForm(forms.Form):

    rallying_cry = forms.CharField(
        label="Rallying Cry",
        min_length=30,
        max_length=1000,
        help_text=(
            "Compose a speech to inspire your soldiers. "
            "Your rallying cry will be judged on leadership, inspiration, "
            "and practicality."
        ),
        widget=forms.Textarea(
            attrs={
                "rows": 8,
                "placeholder": (
                    "Rally your army before battle. "
                    "Your speech will be judged on leadership, "
                    "inspiration, and practicality."
                ),
            }
        ),
    )

    def clean_rallying_cry(self):
        rallying_cry = self.cleaned_data["rallying_cry"].strip()

        if len(rallying_cry) < 30:
            raise forms.ValidationError(
                "Your rallying cry must contain at least 30 characters."
            )

        return rallying_cry