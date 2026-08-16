"""Form used to collect and validate warfare rallying cries.

The warfare system uses the same form for both sides of a conflict:

- the attacker submits a rallying cry while declaring war;
- the defender submits a rallying cry after receiving the declaration.

This is a standard ``forms.Form`` rather than a ``ModelForm`` because the
submitted text is not saved through one fixed model field automatically.
The warfare views decide whether the validated value belongs in
``War.attacker_rallying_cry`` or ``War.defender_rallying_cry`` and then pass
the same text to Gemini for qualitative evaluation.

The form is responsible only for validating and cleaning the player's input.
War creation, AI evaluation, database persistence, and battle resolution remain
the responsibility of the views and dedicated backend services.
"""

from django import forms

from .models import War


class WarForm(forms.Form):
    """Collect and validate a player's pre-battle rallying cry.

    The form is shared by the attacking and defending workflows. It validates
    that the speech contains between 30 and 1,000 characters and returns a
    whitespace-trimmed value through ``cleaned_data``.

    The validated text is consumed by:

    - ``declare_war()``, which stores it as the attacker's rallying cry;
    - ``notify_defender()``, which stores it as the defender's rallying cry;
    - ``evaluate_rallying_cry()``, which asks Gemini to assess leadership,
      inspiration, and practicality.

    This form does not save data itself because the destination model field
    depends on the player's role in the current War.
    """

    rallying_cry = forms.CharField(
        # The label is displayed alongside the textarea when templates render
        # the form using ``form.as_p``.
        label="Rallying Cry",

        # Django's built-in field validation rejects values below this length
        # before ``clean_rallying_cry()`` completes the additional validation.
        min_length=30,

        # The upper limit prevents excessively large submissions from being
        # stored in the War record or included in the Gemini prompt.
        max_length=1000,

        # Both attacker and defender templates render this guidance beneath the
        # field through Django's normal form rendering.
        help_text=(
            "Compose a speech to inspire your soldiers. "
            "Your rallying cry will be judged on leadership, inspiration, "
            "and practicality."
        ),

        # A multiline textarea is more appropriate than a one-line input
        # because players are expected to compose a short speech.
        widget=forms.Textarea(
            attrs={
                # Eight visible rows provide enough room for meaningful input
                # without requiring a large initial page area.
                "rows": 8,

                # The placeholder communicates the evaluation criteria before
                # the player begins typing.
                "placeholder": (
                    "Rally your army before battle. "
                    "Your speech will be judged on leadership, "
                    "inspiration, and practicality."
                ),
            }
        ),
    )

    def clean_rallying_cry(self):
        """Strip surrounding whitespace and enforce the real text length.

        Django's ``min_length`` validation operates on the submitted string,
        but this custom method ensures that leading or trailing whitespace does
        not count as meaningful speech content.

        Returns:
            The validated rallying cry with surrounding whitespace removed.

        Raises:
            forms.ValidationError: If fewer than 30 characters remain after
                whitespace has been stripped.

        Data flow:
            The returned value becomes
            ``form.cleaned_data["rallying_cry"]``. The relevant warfare view
            then stores it on the War and submits it to Gemini.
        """
        # ``cleaned_data`` contains the value after Django has completed the
        # CharField's standard required, length, and string conversion checks.
        rallying_cry = self.cleaned_data["rallying_cry"].strip()

        # Recheck the minimum after stripping so a player cannot satisfy the
        # requirement by surrounding a very short response with spaces.
        if len(rallying_cry) < 30:
            raise forms.ValidationError(
                "Your rallying cry must contain at least 30 characters."
            )

        # Returning the stripped value replaces the original field value inside
        # ``cleaned_data``. Views therefore receive normalised text without
        # needing to trust or process the raw POST value.
        return rallying_cry