from django import forms

from .models import Kingdom, BANNER_CHOICES, CREST_CHOICES, WOLF_CREST_SCORE_REQUIREMENT


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


    def clean_tax_rate(self):
        tax_rate = self.cleaned_data["tax_rate"]
        if tax_rate < 0 or tax_rate > 50:
            raise forms.ValidationError("Tax rate must be between 0 and 50.")
        return tax_rate

    def clean(self):
        cleaned_data = super().clean()
        fields = [
            "agriculture_investment",
            "infrastructure_investment",
            "military_investment",
            "welfare_investment",
        ]

        values = []
        for field in fields:
            value = cleaned_data.get(field)
            if value is None:
                continue
            if value < 0 or value > 100:
                self.add_error(field, "Investment must be between 0 and 100.")
            values.append(value)

        if len(values) == 4 and round(sum(values), 2) != 100:
            raise forms.ValidationError(
                "Agriculture, infrastructure, military, and welfare investments must total 100."
            )

        return cleaned_data


class CreateKingdomForm(forms.ModelForm):
    class Meta:
        model = Kingdom
        fields = ["name"]


class KingdomSettingsForm(forms.ModelForm):
    class Meta:
        model = Kingdom

        fields = [
            "name",
            "ruler_name",
            "banner_colour",
            "crest",
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
            "banner_colour": forms.Select(
                choices=BANNER_CHOICES,
                attrs={
                    "class": "form-control",
                },
            ),
            "crest": forms.Select(
                choices=CREST_CHOICES,
                attrs={
                    "class": "form-control",
                },
            ),
        }

        labels = {
            "name": "Kingdom Name",
            "ruler_name": "Ruler Name",
            "banner_colour": "Royal Banner",
            "crest": "House Crest",
        }

    def __init__(self, *args, **kwargs):
        kingdom = kwargs.pop("kingdom", None)
        super().__init__(*args, **kwargs)

        self.kingdom = kingdom

        if kingdom and not kingdom.is_premium:
            self.fields.pop("banner_colour")
            self.fields.pop("crest")
        elif kingdom:
            crest_choices = list(CREST_CHOICES)
            if not kingdom.has_wolf_crest_unlocked and kingdom.crest != "wolf":
                crest_choices = [
                    choice for choice in crest_choices
                    if choice[0] != "wolf"
                ]
            self.fields["crest"].choices = crest_choices

    def clean_crest(self):
        crest = self.cleaned_data.get("crest")

        if (
            crest == "wolf"
            and self.kingdom
            and not self.kingdom.has_wolf_crest_unlocked
        ):
            raise forms.ValidationError(
                f"The Ice Wolf crest unlocks at a leaderboard score of {WOLF_CREST_SCORE_REQUIREMENT:,}."
            )

        return crest