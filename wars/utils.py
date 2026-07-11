def momentum_hint_for_kingdom(kingdom):
    momentum = kingdom.battle_momentum

    if momentum >= 8:
        return (
            "Scouts report that this army marches with unusual confidence "
            "after a string of recent successes."
        )

    if momentum >= 4:
        return (
            "This kingdom's soldiers appear encouraged by recent campaigns."
        )

    if momentum > -4:
        return (
            "There are no clear signs of unusual confidence or collapse "
            "among this kingdom's forces."
        )

    if momentum > -8:
        return (
            "Reports suggest this army may be carrying the weight of recent setbacks."
        )

    return (
        "Whispers from the border suggest this kingdom's forces are badly shaken "
        "by recent failures."
    )