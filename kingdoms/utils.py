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