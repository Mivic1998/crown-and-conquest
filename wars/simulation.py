import random
from datetime import timedelta
from django.utils import timezone
from .models import Battle, WarCooldown
from core.ai import evaluate_rallying_cry


def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def momentum_modifier_for(kingdom):
    return clamp(1 + (kingdom.battle_momentum / 100), 0.90, 1.10)


def prestige_modifier_for(kingdom):
    return clamp(1 + (kingdom.prestige / 1000), 0.95, 1.05)


def calculate_losses(winner_army, loser_army, closeness):
    winner_loss_rate = 0.08 + (closeness * 0.07)
    loser_loss_rate = 0.20 + ((1 - closeness) * 0.10)

    winner_losses = int(winner_army * winner_loss_rate)
    loser_losses = int(loser_army * loser_loss_rate)

    return winner_losses, loser_losses


def calculate_territory_transfer(winner, loser, closeness):
    base_transfer = 4 + int((1 - closeness) * 6)
    transfer = clamp(base_transfer, 3, 10)
    available = max(0, loser.territory_count - 10)
    return int(min(transfer, available))


def apply_territory_result(winner, loser, closeness):
    territory_transfer = calculate_territory_transfer(winner, loser, closeness)

    winner.territory_count += territory_transfer
    loser.territory_count = max(10, loser.territory_count - territory_transfer)

    return territory_transfer


def update_momentum_and_prestige(attacker, defender, outcome):
    attacker_base = attacker.army_size * attacker.army_quality
    defender_base = defender.army_size * defender.army_quality

    difficulty_ratio = defender_base / attacker_base if attacker_base else 1

    if outcome == "attacker_victory":
        attacker.wars_won += 1
        defender.wars_lost += 1

        if difficulty_ratio < 0.75:
            attacker.battle_momentum += 1
            attacker.prestige -= 3
        elif difficulty_ratio < 1.10:
            attacker.battle_momentum += 4
            attacker.prestige += 3
        else:
            attacker.battle_momentum += 8
            attacker.prestige += 8

        defender.battle_momentum -= 4

    elif outcome == "defender_victory":
        defender.wars_won += 1
        attacker.wars_lost += 1

        defender.battle_momentum += 5
        defender.prestige += 4
        attacker.battle_momentum -= 5
        attacker.prestige -= 2

    else:
        attacker.battle_momentum -= 1
        defender.battle_momentum -= 1

    attacker.battle_momentum = clamp(attacker.battle_momentum, -10, 10)
    defender.battle_momentum = clamp(defender.battle_momentum, -10, 10)

    attacker.prestige = clamp(attacker.prestige, -50, 100)
    defender.prestige = clamp(defender.prestige, -50, 100)


def generate_battle_report(war, outcome, attacker_losses, defender_losses, territory_transfer=0):
    if outcome == "attacker_victory":
        result_text = f"{war.attacker.name} broke through the defending lines and claimed victory."
    elif outcome == "defender_victory":
        result_text = f"{war.defender.name} held firm and repelled the invasion."
    else:
        result_text = "Neither army could secure a decisive victory."

    if war.defender_auto_resolved:
        defender_text = (
            " The defending ruler failed to answer the declaration in time, "
            "and their forces entered battle without a fresh command."
        )
    else:
        defender_text = ""

    if territory_transfer and outcome == "attacker_victory":
        territory_text = f"\n{war.attacker.name} seized {territory_transfer} territories from {war.defender.name}."
    elif territory_transfer and outcome == "defender_victory":
        territory_text = f"\n{war.defender.name} counterclaimed {territory_transfer} territories from {war.attacker.name}."
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

    now = timezone.now()

    if war.status == "resolved":
        return war.battle

    attacker = war.attacker
    defender = war.defender

    defender_auto_resolved = not war.defender_rallying_cry

    if defender_auto_resolved:
        war.defender_auto_resolved = True
        war.defender_rallying_cry = "No rallying cry was given before battle."
        war.defender_rally_modifier = 0.98
        war.defender_ai_feedback = (
            "The defending army received no clear command before battle. "
            "Their forces fought cautiously and without full coordination."
        )
    else:
        defender_ai = evaluate_rallying_cry(war.defender_rallying_cry)

        war.defender_leadership_score = defender_ai["leadership_score"]
        war.defender_inspiration_score = defender_ai["inspiration_score"]
        war.defender_practicality_score = defender_ai["practicality_score"]
        war.defender_rally_modifier = defender_ai["rally_modifier"]
        war.defender_ai_feedback = defender_ai["feedback"]

    attacker_momentum = momentum_modifier_for(attacker)
    defender_momentum = momentum_modifier_for(defender)

    attacker_prestige = prestige_modifier_for(attacker)
    defender_prestige = prestige_modifier_for(defender)

    attacker_random = random.uniform(0.95, 1.05)
    defender_random = random.uniform(0.95, 1.05)

    attacker_strength = (
        attacker.army_size
        * attacker.army_quality
        * war.attacker_rally_modifier
        * attacker_momentum
        * attacker_prestige
        * attacker_random
    )

    defender_strength = (
        defender.army_size
        * defender.army_quality
        * war.defender_rally_modifier
        * defender_momentum
        * defender_prestige
        * defender_random
    )

    if attacker_strength > defender_strength * 1.03:
        outcome = "attacker_victory"
        war.winner = attacker
    elif defender_strength > attacker_strength * 1.03:
        outcome = "defender_victory"
        war.winner = defender
    else:
        outcome = "draw"
        war.winner = None

    weaker_strength = min(attacker_strength, defender_strength)
    stronger_strength = max(attacker_strength, defender_strength)
    closeness = weaker_strength / stronger_strength if stronger_strength else 1
    territory_transfer = 0

    if outcome == "attacker_victory":
        attacker_losses, defender_losses = calculate_losses(
            attacker.army_size,
            defender.army_size,
            closeness,
        )
        territory_transfer = apply_territory_result(attacker, defender, closeness)
    elif outcome == "defender_victory":
        defender_losses, attacker_losses = calculate_losses(
            defender.army_size,
            attacker.army_size,
            closeness,
        )
        territory_transfer = apply_territory_result(defender, attacker, closeness)
    else:
        attacker_losses = int(attacker.army_size * 0.12)
        defender_losses = int(defender.army_size * 0.12)

    if defender_auto_resolved:
        attacker_losses = int(attacker_losses * 0.80)
        defender_losses = int(defender_losses * 0.80)

    attacker.army_size = max(0, attacker.army_size - attacker_losses)
    defender.army_size = max(0, defender.army_size - defender_losses)

    update_momentum_and_prestige(attacker, defender, outcome)

    if defender_auto_resolved:
        attacker.battle_momentum *= 0.75
        defender.battle_momentum *= 0.75
        attacker.prestige *= 0.75
        defender.prestige *= 0.75

    attacker.is_at_war = False
    defender.is_at_war = False
    defender.last_attacked_at = now

    attacker.save()
    defender.save()

    battle_report = generate_battle_report(
        war,
        outcome,
        attacker_losses,
        defender_losses,
        territory_transfer,
    )

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

    war.status = "resolved"
    war.resolved_at = now
    war.save()

    cooldown_until = war.resolved_at + timedelta(hours=24)

    WarCooldown.objects.update_or_create(
        attacker=attacker,
        defender=defender,
        defaults={"cooldown_ends_at": cooldown_until},
    )

    WarCooldown.objects.update_or_create(
        attacker=defender,
        defender=attacker,
        defaults={"cooldown_ends_at": cooldown_until},
    )

    return battle