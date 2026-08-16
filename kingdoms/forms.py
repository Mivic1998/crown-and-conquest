"""Forms for kingdom creation, policy allocation, and realm settings.

This module defines the player-input forms used by the ``kingdoms``
application.

The forms have three separate responsibilities:

- ``PolicyForm`` validates taxation and investment decisions before they are
  saved to the live Kingdom and used by the turn simulation.
- ``CreateKingdomForm`` collects the initial public name of a new realm.
- ``KingdomSettingsForm`` updates kingdom identity fields while restricting
  premium appearance options and score-gated crest choices.

The views remain responsible for ownership, permissions, generated values,
AI calls, simulation processing, and redirects. These forms centralise input
validation and expose only fields that players are permitted to control.
"""

from django import forms

from .models import (
    Kingdom,
    BANNER_CHOICES,
    CREST_CHOICES,
    WOLF_CREST_SCORE_REQUIREMENT,
)


class PolicyForm(forms.ModelForm):#Model forms edit an existing model or data entry 
    """Validate and update the kingdom's current policy allocation.

    This ModelForm is bound to the authenticated player's existing Kingdom
    instance by ``dashboard()``. A valid form updates taxation and the four
    investment percentages stored on that Kingdom.

    The form enforces two levels of policy validation:

    - taxation must remain between 0% and 50%;
    - every investment must remain between 0% and 100%, and the four
      investments must total exactly 100%.

    After the form is saved, the stored policies are used by
    ``process_turn()``. For premium kingdoms, the same validated
    ``cleaned_data`` is also passed to the Gemini-backed policy adviser.
    """

    class Meta:
        """Configure the Kingdom fields editable from the dashboard."""

        model = Kingdom

        # Only policy-related fields are exposed. Ownership, resources,
        # military statistics, premium state, and simulation values cannot be
        # altered through this form.
        fields = [
            "tax_rate",
            "agriculture_investment",
            "infrastructure_investment",
            "military_investment",
            "welfare_investment",
        ]

    def clean_tax_rate(self):
        """Require taxation to remain between 0% and 50%.

        Returns:
            The validated tax rate.

        Raises:
            forms.ValidationError: If the submitted value is below zero or
                above fifty.

        This rule belongs in the form because it governs player-submitted
        policy input. The simulation assumes it receives a valid stored rate
        and does not repeat this validation.
        """
        # Django has already converted the submitted value to the numeric type
        # implied by the Kingdom model field before this method executes.
        tax_rate = self.cleaned_data["tax_rate"]

        # Although the dashboard's HTML range input also uses min=0 and max=50,
        # browser restrictions are not trusted as authoritative validation.
        if tax_rate < 0 or tax_rate > 50:
            raise forms.ValidationError(
                "Tax rate must be between 0 and 50."
            )

        return tax_rate

    def clean(self):
        """Validate all investment ranges and their combined total.

        Field-specific errors are attached to investments outside the permitted
        0–100 range. A non-field error is raised when all four values are
        present but do not total exactly 100%.

        Returns:
            The complete cleaned-data dictionary.

        Raises:
            forms.ValidationError: If the four valid investment values do not
                total 100%.

        The dashboard view calls ``form.is_valid()`` before saving the Kingdom.
        Premium users' validated values are subsequently passed to
        ``evaluate_policy_decision()`` for advisory analysis.
        """
        # Always call the parent implementation first so Django performs model
        # field conversion and any standard field-level validation.
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

            # A missing value may already have produced a field error. Skipping
            # it here avoids performing numeric comparisons against None.
            if value is None:
                continue

            # Attach range errors to the specific field so Django can associate
            # the message with the relevant input.
            if value < 0 or value > 100:
                self.add_error(
                    field,
                    "Investment must be between 0 and 100.",
                )

            values.append(value)

        # Only validate the total when all four values survived initial field
        # processing. This avoids producing a misleading total error alongside
        # missing or non-numeric field errors.
        #
        # Rounding to two decimal places accommodates the FloatField values
        # while still requiring an effective allocation of exactly 100%.
        if len(values) == 4 and round(sum(values), 2) != 100:
            raise forms.ValidationError(
                "Agriculture, infrastructure, military, and welfare "
                "investments must total 100."
            )

        return cleaned_data


class CreateKingdomForm(forms.ModelForm):
    """Collect the public name of a new kingdom.

    The creation form exposes only ``Kingdom.name``. The creation view supplies
    all other required identity and ownership values server-side:

    - ``owner`` comes from the authenticated request;
    - ``ruler_name`` comes from the user's username;
    - ``slug`` is generated from the validated kingdom name.

    Using a ModelForm provides automatic validation for the model field,
    including its maximum length and uniqueness rule.
    """

    class Meta:
        """Expose only the player-controlled kingdom name."""

        model = Kingdom

        # Ownership, ruler name, slug, statistics, and premium values must not
        # be accepted from browser input during kingdom creation.
        fields = ["name"]


class KingdomSettingsForm(forms.ModelForm):
    """Update kingdom identity while enforcing premium and unlock rules.

    Every kingdom may edit its name and ruler name. Banner and crest fields are
    removed entirely for non-premium kingdoms, preventing those values from
    being accepted even if a user manually adds them to a POST request.

    Premium kingdoms may customise their banner and crest. The Ice Wolf crest
    is removed from the available choices until the required leaderboard score
    has been reached, unless the kingdom already has that crest selected.

    The view passes the current Kingdom twice:

    - as ``instance`` so valid data updates the existing record;
    - as the custom ``kingdom`` keyword argument so field availability and
      unlock validation can use the current premium and score state.
    """

    class Meta:
        """Configure editable identity fields and their presentation widgets."""

        model = Kingdom

        fields = [
            "name",
            "ruler_name",
            "banner_colour",
            "crest",
        ]

        # Bootstrap-compatible CSS classes and descriptive placeholders are
        # applied at form construction time. The settings template renders the
        # complete form through ``form.as_p``.
        widgets = {#Controls how fields appear
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
                # Reusing the model choices keeps form options aligned with the
                # values accepted by Kingdom.banner_colour.
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

        # Human-readable labels replace Django's automatically generated names
        # when ``form.as_p`` renders the settings form.
        labels = {
            "name": "Kingdom Name",
            "ruler_name": "Ruler Name",
            "banner_colour": "Royal Banner",
            "crest": "House Crest",
        }

    def __init__(self, *args, **kwargs):#Used to customise the form when it is initialiased so it can vary based on whether user is premium
        """Configure fields according to the current kingdom's entitlement.

        Args:
            *args: Standard positional arguments accepted by ModelForm.
            **kwargs: Standard ModelForm arguments plus the custom
                ``kingdom`` keyword argument.

        Side effects:
            - removes premium-only fields for standard kingdoms;
            - removes the locked wolf crest from eligible field choices;
            - stores the supplied kingdom on ``self`` for later validation.

        The custom ``kingdom`` value is removed before calling ``super()``
        because Django's base ModelForm does not recognise that keyword.
        """
        # Extract application-specific context before delegating standard form
        # initialisation to Django.
        kingdom = kwargs.pop("kingdom", None)
        super().__init__(*args, **kwargs)

        # ``clean_crest()`` later uses this reference to verify the unlock rule
        # even if a malicious POST manually supplies the hidden choice.
        self.kingdom = kingdom

        if kingdom and not kingdom.is_premium:
            # Removing fields is stronger than merely hiding them in the
            # template. Django will not accept or save submitted banner or crest
            # values when they are absent from the form definition.
            self.fields.pop("banner_colour")
            self.fields.pop("crest")

        elif kingdom:
            # Copy the shared choices before filtering so the module-level
            # constant is not mutated for later form instances.
            crest_choices = list(CREST_CHOICES)

            # A locked kingdom should not be offered the wolf crest. The second
            # condition preserves the choice for a kingdom that already owns it,
            # preventing an existing valid selection from disappearing.
            if (
                not kingdom.has_wolf_crest_unlocked
                and kingdom.crest != "wolf"
            ):
                crest_choices = [
                    choice
                    for choice in crest_choices
                    if choice[0] != "wolf"
                ]

            self.fields["crest"].choices = crest_choices

    def clean_crest(self):
        """Prevent selection of the wolf crest before it is unlocked.

        Returns:
            The submitted crest value.

        Raises:
            forms.ValidationError: If a kingdom attempts to select the wolf
                crest before reaching the required leaderboard score.

        Removing the option in ``__init__`` improves the interface, while this
        method provides server-side business-rule validation against manually
        constructed POST data.
        """
        # ``get`` safely returns None when the crest field was removed for a
        # non-premium kingdom.
        crest = self.cleaned_data.get("crest")

        if (
            crest == "wolf"
            and self.kingdom
            and not self.kingdom.has_wolf_crest_unlocked
        ):
            raise forms.ValidationError(
                f"The Ice Wolf crest unlocks at a leaderboard score of "
                f"{WOLF_CREST_SCORE_REQUIREMENT:,}."
            )

        return crest