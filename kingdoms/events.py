from .models import Kingdom
import random

EVENT_EFFECTS = {
    "famine": {
        "description": (
            "Poor harvests and adverse weather have devastated crops "
            "throughout the realm. Food production will be severely reduced."
        ),
        "turns": 3,
        "production_modifier": 0.35,
        "population_percent": -0.03,
        "happiness": -8,
        "stability": -5,
    },

    "riot": {
        "description": (
            "Unrest has erupted in the kingdom's towns and cities. "
            "Merchants refuse to trade and property has been damaged."
        ),
        "treasury": -300,
        "happiness": -6,
        "stability": -10,
    },

    "rebellion": {
        "description": (
            "A faction of nobles has risen against the crown, "
            "threatening the stability of the realm."
        ),
        "army_size_percent": -0.08,
        "stability": -15,
        "happiness": -10,
    },

    "market_crash": {
        "description": (
            "Trade has collapsed and confidence in the kingdom's economy "
            "has been shaken."
        ),
        "treasury_percent": -0.15,
        "happiness": -4,
        "stability": -6,
    },

    "desertion": {
        "description": (
            "Large numbers of soldiers have deserted the army, "
            "reducing military effectiveness."
        ),
        "army_size_percent": -0.12,
        "army_quality": -2,
        "stability": -4,
    },
}

def evaluate_events(kingdom):
    
    tax_rate = kingdom.tax_rate
    
    available_food = kingdom.food
    food_needed = kingdom.population
    food_balance = available_food - food_needed

    happiness = kingdom.happiness
    stability = kingdom.stability

    famine_probability = 0.02 + max(0, -food_balance/food_needed) * 0.5

    if kingdom.famine_turns_remaining > 0:
        famine_probability = 0    

    probabilities = {
        "famine": famine_probability,
        "riot": 0.03 + (100 - happiness)/100 * 0.2 + (100 - stability)/100 * 0.2,
        "rebellion": max(0, (50 - stability)/100 + (50 - happiness)/100) * 0.4,
        "market": 0.02 + (tax_rate/100 * 0.2) + ((100 - stability)/100 * 0.3),
        "desertion": (100 - happiness)/100 * 0.3
    }

    roll = random.uniform(0, 1)

    max_probability = 0
    event = None

    for key, value in probabilities.items():
        if roll < value and value > max_probability:
            event = key    
            max_probability = value

    return event        

def apply_event_response_effects(event):
    """
    Apply event effects after the player's response has been evaluated.

    The event type determines which penalties apply.
    The AI score determines how severe those penalties are.
    """

    kingdom = event.kingdom

    score = event.ai_score or 0
    score = max(0, min(score, 10))

    severity = 1 - (score / 10)

    effects = EVENT_EFFECTS[event.event_type]

    if event.event_type == "famine":
        kingdom.famine_turns_remaining += max(
            1,
            int(effects["turns"] * severity)
        )

        kingdom.famine_production_modifier *= (
            1 - (
                (1 - effects["production_modifier"])
                * severity
            )
        )

        kingdom.happiness += (
            effects["happiness"] * severity
        )

        kingdom.stability += (
            effects["stability"] * severity
        )

        kingdom.population = int(
            kingdom.population
            * (1 + effects["population_percent"] * severity)
        )

    elif event.event_type == "riot":
        kingdom.treasury += (
            effects["treasury"] * severity
        )

        kingdom.happiness += (
            effects["happiness"] * severity
        )

        kingdom.stability += (
            effects["stability"] * severity
        )

    elif event.event_type == "rebellion":
        kingdom.population = int(
            kingdom.population
            * (1 + effects["population_percent"] * severity)
        )

        kingdom.army_size = int(
            kingdom.army_size
            * (1 + effects["army_size_percent"] * severity)
        )

        kingdom.happiness += (
            effects["happiness"] * severity
        )

        kingdom.stability += (
            effects["stability"] * severity
        )

    elif event.event_type == "market_crash":
        kingdom.treasury = int(
            kingdom.treasury
            * (1 + effects["treasury_percent"] * severity)
        )

        kingdom.happiness += (
            effects["happiness"] * severity
        )

        kingdom.stability += (
            effects["stability"] * severity
        )

    elif event.event_type == "desertion":
        kingdom.army_size = int(
            kingdom.army_size
            * (1 + effects["army_size_percent"] * severity)
        )

        kingdom.army_quality += (
            effects["army_quality"] * severity
        )

        kingdom.stability += (
            effects["stability"] * severity
        )

    kingdom.save()