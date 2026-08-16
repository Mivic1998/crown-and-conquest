"""Authoritative battle-resolution logic for the warfare system.

This module converts one pending ``War`` into a completed ``Battle`` while
updating both participating Kingdom records and creating the cooldowns that
govern future diplomacy.

The simulation combines:

- army size and army quality;
- Gemini-derived rally modifiers;
- recent battle momentum;
- accumulated prestige;
- bounded random variation;
- a three-percent victory threshold;
- casualty and territory-transfer rules.

The simulation remains server-authoritative. Gemini contributes only a bounded
rally modifier, while Django determines the final strengths, outcome, losses,
territory transfer, momentum, prestige, narrative, and database state.

The helper functions separate individual formulas from the main resolution
pipeline, making each rule easier to explain and test independently.
"""

import random
from datetime import timedelta

from django.utils import timezone

from .models import Battle, WarCooldown
from core.ai import evaluate_rallying_cry


def clamp(value, minimum, maximum):
    """Restrict a numeric value to an inclusive range.

    Args:
        value: The value being constrained.
        minimum: The lowest permitted result.
        maximum: The highest permitted result.

    Returns:
        ``value`` when it lies inside the range, otherwise the nearest boundary.

    Used by:
        - momentum modifier calculation;
        - prestige modifier calculation;
        - territory-transfer calculation;
        - persistent momentum and prestige updates.
    """
    return max(minimum, min(value, maximum))


def momentum_modifier_for(kingdom):
    """Convert stored battle momentum into a bounded strength multiplier.

    ``Kingdom.battle_momentum`` normally remains between -10 and 10. Dividing
    it by 100 converts that state into a maximum combat adjustment of roughly
    minus or plus ten percent.

    Args:
        kingdom: The attacking or defending Kingdom.

    Returns:
        A multiplier between ``0.90`` and ``1.10``.

    The returned modifier is used in final-strength calculation and is later
    stored on the Battle for auditability.
    """
    # A momentum value of 0 produces the neutral multiplier 1.0.
    # Positive momentum increases strength and negative momentum reduces it.
    return clamp(
        1 + (kingdom.battle_momentum / 100),
        0.90,
        1.10,
    )


def prestige_modifier_for(kingdom):
    """Convert stored prestige into a bounded combat multiplier.

    Prestige has a deliberately smaller effect than momentum. Dividing by
    1,000 converts the model's -50 to 100 range into a theoretical modifier
    from 0.95 to 1.10, after which the upper bound is limited to 1.05.

    Args:
        kingdom: The Kingdom whose prestige should be converted.

    Returns:
        A multiplier between ``0.95`` and ``1.05``.

    The value influences the current battle and is stored on the resulting
    Battle record.
    """
    return clamp(
        1 + (kingdom.prestige / 1000),
        0.95,
        1.05,
    )


def calculate_losses(winner_army, loser_army, closeness):
    """Calculate casualties for a decisive battle outcome.

    The winner's loss rate increases when the battle was close. The loser's
    loss rate increases when the battle was one-sided.

    Args:
        winner_army: Winner's army size before casualties.
        loser_army: Loser's army size before casualties.
        closeness: Ratio of weaker final strength to stronger final strength,
            normally between 0 and 1.

    Returns:
        A tuple containing ``winner_losses`` and ``loser_losses``.

    Formula:
        - winner rate = 8% + closeness × 7%
        - loser rate = 20% + (1 - closeness) × 10%

    This produces:

        - winner losses between approximately 8% and 15%;
        - loser losses between approximately 20% and 30%.
    """
    # A close battle raises the cost paid by the winner.
    winner_loss_rate = 0.08 + (closeness * 0.07)

    # A one-sided battle raises the losing army's casualty rate.
    loser_loss_rate = 0.20 + ((1 - closeness) * 0.10)

    # Casualties are converted to whole soldiers because army size is stored as
    # an integer on Kingdom.
    winner_losses = int(winner_army * winner_loss_rate)
    loser_losses = int(loser_army * loser_loss_rate)

    return winner_losses, loser_losses


def calculate_territory_transfer(winner, loser, closeness):
    """Calculate how many territories may move to the victorious kingdom.

    More decisive victories transfer more territory, but the losing kingdom is
    never allowed to fall below ten territories.

    Args:
        winner: Victorious Kingdom. The current formula does not directly read
            this object, but it is part of the helper's domain-oriented API.
        loser: Defeated Kingdom whose territory availability is checked.
        closeness: Ratio of weaker to stronger final strength.

    Returns:
        The number of territories to transfer as an integer.

    Formula:
        ``4 + int((1 - closeness) * 6)``, bounded between 3 and 10, then limited
        by the loser's territory above the protected minimum of ten.
    """
    # A close battle produces a transfer near four, while increasingly decisive
    # victories can move up to approximately ten territories.
    base_transfer = 4 + int((1 - closeness) * 6)

    # The explicit clamp protects the rule if future callers provide an unusual
    # closeness value.
    transfer = clamp(base_transfer, 3, 10)

    # Preserve a minimum realm size of ten territories for the defeated kingdom.
    available = max(0, loser.territory_count - 10)

    # Transfer no more territory than the loser can legally surrender.
    return int(min(transfer, available))


def apply_territory_result(winner, loser, closeness):
    """Apply a calculated territory transfer to both Kingdom objects.

    Args:
        winner: Kingdom receiving territory.
        loser: Kingdom surrendering territory.
        closeness: Final-strength ratio used to determine transfer size.

    Returns:
        The number of territories transferred.

    Side effects:
        Mutates ``winner.territory_count`` and ``loser.territory_count`` in
        memory. The caller later persists both Kingdom records.

    The returned number is included in the generated battle narrative.
    """
    territory_transfer = calculate_territory_transfer(
        winner,
        loser,
        closeness,
    )

    winner.territory_count += territory_transfer

    # The second minimum check guarantees that the loser remains at or above ten
    # even if future calculation changes produce an unexpected transfer.
    loser.territory_count = max(
        10,
        loser.territory_count - territory_transfer,
    )

    return territory_transfer


def update_momentum_and_prestige(attacker, defender, outcome):
    """Update war records, momentum, and prestige after the outcome.

    Attacker victory rewards depend on how difficult the original military
    matchup was. Defenders receive a fixed reward for successfully resisting an
    invasion, while draws slightly reduce both sides' momentum.

    Args:
        attacker: Attacking Kingdom.
        defender: Defending Kingdom.
        outcome: One of ``attacker_victory``, ``defender_victory``, or ``draw``.

    Side effects:
        Mutates, but does not immediately save:

        - ``wars_won``;
        - ``wars_lost``;
        - ``battle_momentum``;
        - ``prestige``.

    The caller saves both Kingdom records later in the resolution pipeline.
    """
    # Difficulty is measured from the pre-casualty army size and quality stored
    # on each live Kingdom. Rally, momentum, prestige, and random factors are
    # not included in this reward classification.
    attacker_base = attacker.army_size * attacker.army_quality
    defender_base = defender.army_size * defender.army_quality

    # Avoid division by zero if the attacker enters resolution with no effective
    # base strength.
    difficulty_ratio = (
        defender_base / attacker_base
        if attacker_base
        else 1
    )

    if outcome == "attacker_victory":
        attacker.wars_won += 1
        defender.wars_lost += 1

        # Defeating a substantially weaker target gives only a minor momentum
        # reward and imposes a prestige penalty.
        if difficulty_ratio < 0.75:
            attacker.battle_momentum += 1
            attacker.prestige -= 3

        # Winning against a broadly comparable opponent gives moderate rewards.
        elif difficulty_ratio < 1.10:
            attacker.battle_momentum += 4
            attacker.prestige += 3

        # Defeating a stronger opponent gives the largest reward.
        else:
            attacker.battle_momentum += 8
            attacker.prestige += 8

        defender.battle_momentum -= 4

    elif outcome == "defender_victory":
        defender.wars_won += 1
        attacker.wars_lost += 1

        # Successful defence receives a fixed momentum and prestige reward.
        defender.battle_momentum += 5
        defender.prestige += 4

        attacker.battle_momentum -= 5
        attacker.prestige -= 2

    else:
        # A draw counts as neither a win nor a loss but reduces confidence for
        # both armies.
        attacker.battle_momentum -= 1
        defender.battle_momentum -= 1

    # Bound persistent values so repeated warfare cannot produce unlimited
    # compounding modifiers.
    attacker.battle_momentum = clamp(
        attacker.battle_momentum,
        -10,
        10,
    )
    defender.battle_momentum = clamp(
        defender.battle_momentum,
        -10,
        10,
    )

    attacker.prestige = clamp(
        attacker.prestige,
        -50,
        100,
    )
    defender.prestige = clamp(
        defender.prestige,
        -50,
        100,
    )


def generate_battle_report(
    war,
    outcome,
    attacker_losses,
    defender_losses,
    territory_transfer=0,
):
    """Build the narrative stored on the completed Battle.

    Args:
        war: War containing participants and timeout state.
        outcome: Final battle outcome.
        attacker_losses: Attacking army casualties.
        defender_losses: Defending army casualties.
        territory_transfer: Number of transferred territories.

    Returns:
        A formatted narrative string.

    The result is stored in ``Battle.battle_report`` and rendered with
    Django's ``linebreaks`` filter in ``wars/battle_report.html``.
    """
    if outcome == "attacker_victory":
        result_text = (
            f"{war.attacker.name} broke through the defending lines "
            f"and claimed victory."
        )
    elif outcome == "defender_victory":
        result_text = (
            f"{war.defender.name} held firm and repelled the invasion."
        )
    else:
        result_text = "Neither army could secure a decisive victory."

    # Add a timeout explanation when the defender entered combat without a
    # submitted rallying cry.
    if war.defender_auto_resolved:
        defender_text = (
            " The defending ruler failed to answer the declaration in time, "
            "and their forces entered battle without a fresh command."
        )
    else:
        defender_text = ""

    # Describe which side gained territory. Draws and victories where no
    # territory was available explicitly state that no land changed hands.
    if territory_transfer and outcome == "attacker_victory":
        territory_text = (
            f"\n{war.attacker.name} seized {territory_transfer} "
            f"territories from {war.defender.name}."
        )
    elif territory_transfer and outcome == "defender_victory":
        territory_text = (
            f"\n{war.defender.name} counterclaimed {territory_transfer} "
            f"territories from {war.attacker.name}."
        )
    else:
        territory_text = "\nNo territories changed hands."

    return (
        f"{result_text}\n\n"
        f"{war.attacker.name} lost {attacker_losses} soldiers.\n"
        f"{war.defender.name} lost {defender_losses} soldiers."
        f"{territory_text}"
        f"{defender_text}"
    )


def resolve_war_simulation(war):
    """Resolve one pending War and persist the complete result.

    The function is the authoritative warfare state transition. It combines
    military data, stored attacker AI evaluation, defender AI evaluation or
    timeout fallback, momentum, prestige, and controlled randomness.

    Args:
        war: The pending War to resolve.

    Returns:
        The newly created Battle, or the existing related Battle when the War
        has already been resolved.

    Side effects:
        - may evaluate and update defender rallying-cry fields;
        - mutates and saves both Kingdom records;
        - creates one Battle;
        - marks the War resolved and saves it;
        - creates or updates two directional WarCooldown records.

    Calculation order matters because:

        1. all strength inputs must be captured before casualties;
        2. outcome must be known before losses and territory transfer;
        3. live Kingdom values must be updated before the final report is shown;
        4. the Battle must preserve the original modifiers and calculated
           strengths even after the Kingdom records change.
    """
    # Capture one authoritative server timestamp for resolution and cooldown
    # calculations.
    now = timezone.now()

    # Idempotency guard: repeat calls return the existing one-to-one Battle
    # instead of creating another result or applying losses twice.
    if war.status == "resolved":
        return war.battle

    attacker = war.attacker
    defender = war.defender

    # A missing defender speech triggers the deterministic timeout fallback.
    # The code checks for an empty rallying-cry value rather than the deadline
    # itself because the calling workflow decides when resolution may begin.
    defender_auto_resolved = not war.defender_rallying_cry

    if defender_auto_resolved:
        # Persist an explicit timeout state so the Battle report can distinguish
        # it from a submitted defender response.
        war.defender_auto_resolved = True
        war.defender_rallying_cry = (
            "No rallying cry was given before battle."
        )

        # The timeout modifier is a small two-percent disadvantage rather than
        # an automatic defeat.
        war.defender_rally_modifier = 0.98

        war.defender_ai_feedback = (
            "The defending army received no clear command before battle. "
            "Their forces fought cautiously and without full coordination."
        )

    else:
        # Re-evaluate the saved defender speech at resolution time. The returned
        # Gemini data is validated and bounded by ``evaluate_rallying_cry()``,
        # which also supplies 4/10 scores and a 0.98 modifier on API failure.
        defender_ai = evaluate_rallying_cry(
            war.defender_rallying_cry
        )

        war.defender_leadership_score = (
            defender_ai["leadership_score"]
        )
        war.defender_inspiration_score = (
            defender_ai["inspiration_score"]
        )
        war.defender_practicality_score = (
            defender_ai["practicality_score"]
        )
        war.defender_rally_modifier = (
            defender_ai["rally_modifier"]
        )
        war.defender_ai_feedback = defender_ai["feedback"]

    # Convert each kingdom's persistent strategic history into bounded
    # multiplicative factors before casualties or post-battle updates alter it.
    attacker_momentum = momentum_modifier_for(attacker)
    defender_momentum = momentum_modifier_for(defender)

    attacker_prestige = prestige_modifier_for(attacker)
    defender_prestige = prestige_modifier_for(defender)

    # Introduce independent variation of at most minus or plus five percent.
    # The exact values are stored on Battle so the stochastic result remains
    # inspectable after resolution.
    attacker_random = random.uniform(0.95, 1.05)
    defender_random = random.uniform(0.95, 1.05)

    # Final strength multiplies troop quantity by quality and every bounded
    # modifier. The attacker rally value was stored during declaration.
    attacker_strength = (
        attacker.army_size
        * attacker.army_quality
        * war.attacker_rally_modifier
        * attacker_momentum
        * attacker_prestige
        * attacker_random
    )

    # The defender uses either the submitted-and-evaluated rally modifier or the
    # 0.98 timeout fallback assigned above.
    defender_strength = (
        defender.army_size
        * defender.army_quality
        * war.defender_rally_modifier
        * defender_momentum
        * defender_prestige
        * defender_random
    )

    # A side must exceed the opponent by more than three percent to win.
    # Results within that margin are recorded as draws, preventing tiny floating
    # point or random differences from always producing a victor.
    if attacker_strength > defender_strength * 1.03:
        outcome = "attacker_victory"
        war.winner = attacker
    elif defender_strength > attacker_strength * 1.03:
        outcome = "defender_victory"
        war.winner = defender
    else:
        outcome = "draw"
        war.winner = None

    # Closeness is always the weaker final strength divided by the stronger.
    # Equal strengths produce 1; increasingly one-sided battles approach 0.
    weaker_strength = min(
        attacker_strength,
        defender_strength,
    )
    stronger_strength = max(
        attacker_strength,
        defender_strength,
    )
    closeness = (
        weaker_strength / stronger_strength
        if stronger_strength
        else 1
    )

    territory_transfer = 0

    if outcome == "attacker_victory":
        # calculate_losses() returns winner losses first and loser losses second.
        attacker_losses, defender_losses = calculate_losses(
            attacker.army_size,
            defender.army_size,
            closeness,
        )

        # Mutate territory in memory; both Kingdom records are saved later.
        territory_transfer = apply_territory_result(
            attacker,
            defender,
            closeness,
        )

    elif outcome == "defender_victory":
        # The defender is passed as the winner, so the returned tuple must be
        # assigned in defender-then-attacker order.
        defender_losses, attacker_losses = calculate_losses(
            defender.army_size,
            attacker.army_size,
            closeness,
        )

        territory_transfer = apply_territory_result(
            defender,
            attacker,
            closeness,
        )

    else:
        # Draws apply a fixed twelve-percent loss to both armies rather than
        # using the winner/loser casualty formula.
        attacker_losses = int(attacker.army_size * 0.12)
        defender_losses = int(defender.army_size * 0.12)

    if defender_auto_resolved:
        # Timeout battles reduce both sides' calculated casualties by twenty
        # percent. This limits the consequences of a conflict resolved without a
        # full defender interaction.
        attacker_losses = int(attacker_losses * 0.80)
        defender_losses = int(defender_losses * 0.80)

    # Apply casualties to the live Kingdom records while preventing negative
    # army sizes.
    attacker.army_size = max(
        0,
        attacker.army_size - attacker_losses,
    )
    defender.army_size = max(
        0,
        defender.army_size - defender_losses,
    )

    # Record wins/losses and calculate post-battle strategic consequences.
    # This occurs after casualties, so the difficulty ratio inside that helper
    # uses the remaining army sizes rather than the original pre-battle sizes.
    update_momentum_and_prestige(
        attacker,
        defender,
        outcome,
    )

    if defender_auto_resolved:
        # Reduce both sides' momentum and prestige impact when the defender did
        # not actively participate. The values had already been clamped before
        # this proportional reduction.
        attacker.battle_momentum *= 0.75
        defender.battle_momentum *= 0.75
        attacker.prestige *= 0.75
        defender.prestige *= 0.75

    # The conflict is no longer active for either participant.
    attacker.is_at_war = False
    defender.is_at_war = False

    # The defender receives a global two-hour protection check elsewhere in the
    # declaration view based on this timestamp.
    defender.last_attacked_at = now

    # Persist all changed Kingdom values: armies, territories, records,
    # momentum, prestige, war flags, and defender attack time.
    attacker.save()
    defender.save()

    # Generate the visible narrative after all outcome, loss, timeout, and
    # territory values are known.
    battle_report = generate_battle_report(
        war,
        outcome,
        attacker_losses,
        defender_losses,
        territory_transfer,
    )

    # Store the complete result. Hidden factors and final strengths are
    # preserved even though the current template shows only outcome, losses,
    # narrative, remaining armies, and rally assessments.
    battle = Battle.objects.create(
        war=war,
        attacker=attacker,
        defender=defender,
        attacker_momentum_modifier=attacker_momentum,
        defender_momentum_modifier=defender_momentum,
        attacker_prestige_modifier=attacker_prestige,
        defender_prestige_modifier=defender_prestige,
        attacker_random_factor=attacker_random,
        defender_random_factor=defender_random,
        attacker_strength=attacker_strength,
        defender_strength=defender_strength,
        outcome=outcome,
        attacker_losses=attacker_losses,
        defender_losses=defender_losses,
        battle_report=battle_report,
    )

    # Complete the War lifecycle only after the Battle has been created.
    # ``war.save()`` also persists winner and all defender fallback or
    # re-evaluation fields changed earlier in the function.
    war.status = "resolved"
    war.resolved_at = now
    war.save()

    # Participants receive mutual directional cooldowns lasting 24 hours from
    # resolution.
    cooldown_until = war.resolved_at + timedelta(hours=24)

    # update_or_create() reuses an existing directional record for a rematch
    # rather than violating WarCooldown's attacker/defender uniqueness rule.
    WarCooldown.objects.update_or_create(
        attacker=attacker,
        defender=defender,
        defaults={
            "cooldown_ends_at": cooldown_until,
        },
    )

    WarCooldown.objects.update_or_create(
        attacker=defender,
        defender=attacker,
        defaults={
            "cooldown_ends_at": cooldown_until,
        },
    )

    return battle