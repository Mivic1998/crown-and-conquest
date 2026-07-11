from datetime import datetime, time, timedelta
from django.utils import timezone

def next_midnight():
    now = timezone.localtime()
    tomorrow = now.date() + timedelta(days=1)

    midnight = datetime.combine(
        tomorrow,
        time.min
    )

    return timezone.make_aware(
        midnight,
        timezone.get_current_timezone()
    )

def build_effect_comparison(original, applied):
    rows = []

    labels = {
        "population_percent": "Population",
        "treasury": "Treasury",
        "treasury_percent": "Treasury",
        "army_size_percent": "Army Size",
        "army_quality": "Army Quality",
        "happiness": "Happiness",
        "stability": "Stability",
        "turns": "Duration",
        "production_modifier": "Food Production",
    }

    for key, label in labels.items():

        if key in original or key in applied:

            original_value = original.get(key, 0)
            applied_value = applied.get(key, 0)

            rows.append({
                "label": label,
                "original": original_value,
                "applied": applied_value,
                "mitigated": applied_value - original_value,
            })

    return rows

def calculate_score(empathy, practicality, leadership):
    return (
        empathy * 0.2
        + practicality * 0.3
        + leadership * 0.5
    )

