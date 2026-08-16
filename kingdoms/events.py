"""Dynamic event selection and consequence application for kingdoms.

This module defines the major crises that can occur after a kingdom completes
a turn. It has two separate responsibilities:

- ``evaluate_events()`` examines the kingdom's current state and probabilistically
  selects at most one eligible event type.
- ``apply_event_response_effects()`` scales the selected event's predefined
  consequences according to the player's AI-evaluated response and applies
  those consequences to the live Kingdom.

The module does not create Event database records itself. Turn processing
returns an event-type key to the view, which creates the Event and links it to
the relevant TurnHistory snapshot. The response view later stores the player's
decree and AI evaluation before calling the effect-application function.

Gemini never mutates the Kingdom directly. Django converts the stored AI score
into a bounded severity value and remains authoritative over every gameplay
effect and database write.
"""

from .models import Kingdom
import random


# Centralise event narratives and base effects so event selection, persistence,
# effect application, and report comparison all reference the same definitions.
#
# Negative values represent harmful changes. Percentage keys are applied
# proportionally to the current model value, whereas keys such as ``treasury``,
# ``happiness``, and ``stability`` are applied as direct numerical changes.
EVENT_EFFECTS = {
    "famine": {
        # The description is copied into Event.description when the turn view
        # creates the persistent event record. It is later shown on response,
        # history, and completed report pages.
        "description": (
            "Poor harvests and adverse weather have devastated crops "
            "throughout the realm. Food production will be severely reduced."
        ),

        # Famine is the only current event with a persistent multi-turn effect.
        "turns": 3,

        # A value of 0.35 means unmitigated production falls to 35% of normal.
        "production_modifier": 0.35,

        # Percentage-based effects are multiplied against the current population.
        "population_percent": -0.1,

        # These are direct changes to percentage-like social metrics.
        "happiness": -8,
        "stability": -5,
    },

    "riot": {
        "description": (
            "Unrest has erupted in the kingdom's towns and cities. "
            "Merchants refuse to trade and property has been damaged."
        ),

        # Riot treasury damage is a fixed amount rather than a percentage.
        "treasury": -300,
        "happiness": -6,
        "stability": -10,
    },

    "rebellion": {
        "description": (
            "A faction of nobles has risen against the crown, "
            "threatening the stability of the realm."
        ),

        # Rebellion damages both civilian population and army size
        # proportionally to their current values.
        "population_percent": -0.03,
        "army_size_percent": -0.08,
        "stability": -15,
        "happiness": -10,
    },

    "market_crash": {
        "description": (
            "Trade has collapsed and confidence in the kingdom's economy "
            "has been shaken."
        ),

        # Market crashes remove a proportion of the current treasury, meaning
        # wealthier kingdoms lose a larger absolute amount.
        "treasury_percent": -0.15,
        "happiness": -4,
        "stability": -6,
    },

    "desertion": {
        "description": (
            "Large numbers of soldiers have deserted the army, "
            "reducing military effectiveness."
        ),

        # Desertion reduces both troop quantity and army quality.
        "army_size_percent": -0.12,
        "army_quality": -2,
        "stability": -4,
    },
}


def evaluate_events(kingdom):
    """Select at most one event after a completed kingdom turn.

    Event probabilities are calculated from the Kingdom's newly updated state.
    One shared random value is then compared against every event probability.
    If several events pass that roll, the event with the highest probability is
    returned.

    Args:
        kingdom: The live Kingdom after ``process_turn()`` has completed and
            saved its economic, demographic, and social calculations.

    Returns:
        The string key of the selected event from ``EVENT_EFFECTS``, or ``None``
        when no event passes the probability check.

    Side effects:
        None. This function does not create an Event or alter the Kingdom.

    Called from:
        ``process_turn()``. The resulting event key is returned to
        ``take_turn()``, which creates the Event and links it to TurnHistory.
    """
    # Taxation contributes to market-crash risk.
    tax_rate = kingdom.tax_rate

    # ``Kingdom.food`` represents the stored reserve left by turn processing.
    # It is compared with current population to estimate whether the kingdom
    # holds enough food to cover one population-equivalent requirement.
    available_food = kingdom.food
    food_needed = kingdom.population
    food_balance = available_food - food_needed

    # Happiness and stability influence several unrest-related probabilities.
    happiness = kingdom.happiness
    stability = kingdom.stability

    # Famine begins with a baseline 2% chance. A food deficit increases that
    # chance proportionally, with the deficit ratio contributing up to and
    # potentially beyond the baseline depending on kingdom state.
    famine_probability = (
        0.02
        + max(0, -food_balance / food_needed) * 0.5
    )

    # Prevent a second famine event from being selected while an existing
    # persistent famine remains active.
    if kingdom.famine_turns_remaining > 0:
        famine_probability = 0

    probabilities = {
        "famine": famine_probability,

        # Riot risk rises independently as happiness and stability fall.
        "riot": (
            0.03
            + (100 - happiness) / 100 * 0.2
            + (100 - stability) / 100 * 0.2
        ),

        # Rebellion only gains probability when happiness or stability falls
        # below 50. The combined shortfall is multiplied by 40%.
        "rebellion": (
            max(
                0,
                (50 - stability) / 100
                + (50 - happiness) / 100,
            )
            * 0.4
        ),

        # Market-crash risk has a 2% baseline and rises with taxation and
        # instability.
        "market_crash": (
            0.02
            + (tax_rate / 100 * 0.2)
            + ((100 - stability) / 100 * 0.3)
        ),

        # This is deliberately fixed at 1 while the desertion workflow is being
        # tested. The intended production formula is:
        #
        #     (100 - happiness) / 100 * 0.3
        #
        # With the current value, desertion always passes the shared random roll
        # and will be selected unless another event has a probability above 1.
        "desertion": 1,
    }

    # One shared roll preserves the rule that at most one event is returned.
    # It also means events compete by calculated probability rather than each
    # receiving an independent random trial.
    roll = random.uniform(0, 1)

    max_probability = 0
    event = None

    # Dictionary insertion order defines the tie behaviour. A later event only
    # replaces the current choice when its probability is strictly greater, so
    # equal probabilities preserve the first matching event.
    for key, value in probabilities.items():
        if roll < value and value > max_probability:
            event = key
            max_probability = value

    return event


def apply_event_response_effects(event):
    """Scale and apply an Event's consequences to its Kingdom.

    The Event must already contain the final application-controlled ``ai_score``
    calculated by the response view. That score is clamped to 0–10 and converted
    into severity:

        severity = 1 - score / 10

    A score of 0 applies the full predefined effect. A score of 10 produces
    zero ordinary severity, although famine duration is still forced to at
    least one turn.

    Args:
        event: The resolved Event whose ``event_type``, ``ai_score``, and
            related Kingdom determine the effects to apply.

    Returns:
        None.

    Side effects:
        - mutates and saves the related Kingdom;
        - stores the exact scaled values in ``Event.applied_effects``;
        - saves that JSON field on the Event.

    The stored applied-effects dictionary is later compared with the original
    ``EVENT_EFFECTS`` definition in the completed event report.
    """
    kingdom = event.kingdom

    # The event type was selected by evaluate_events() and persisted by the
    # turn view. It is used as the key into the central effect definition.
    effects = EVENT_EFFECTS[event.event_type]

    # A missing or falsy score is treated as zero, applying full severity.
    # The response workflow normally assigns a score before calling this
    # function.
    score = event.ai_score or 0

    # Defensive clamping prevents any score outside the expected 0–10 range
    # from reversing effects or increasing mitigation beyond the design limits.
    score = max(0, min(score, 10))

    # Higher-quality responses reduce the magnitude of the crisis.
    #
    # Score 0  → severity 1.0 → 100% of base consequences
    # Score 5  → severity 0.5 → 50% of base consequences
    # Score 10 → severity 0.0 → ordinary effects fully mitigated
    severity = 1 - (score / 10)

    # This dictionary records the exact consequences used for the current
    # kingdom. It is persisted on Event and later displayed beside the original
    # unmitigated values in event_detail.html.
    applied = {}

    if event.event_type == "famine":
        applied = {
            # Duration scales down with severity but is always at least one
            # turn, even when the player's score reaches ten.
            "turns": max(
                1,
                int(effects["turns"] * severity),
            ),

            # Interpolate between normal production (1.0) and the base famine
            # modifier. At full severity the result is 0.35; at zero severity
            # it is 1.0.
            "production_modifier": (
                1
                - (
                    (1 - effects["production_modifier"])
                    * severity
                )
            ),

            "happiness": effects["happiness"] * severity,
            "stability": effects["stability"] * severity,
            "population_percent": (
                effects["population_percent"] * severity
            ),
        }

        # Add duration rather than replacing it. The selection function normally
        # prevents famine while one is active, but additive behaviour preserves
        # any existing duration if this function is called manually or through
        # another workflow.
        kingdom.famine_turns_remaining += applied["turns"]

        # Multiply persistent production modifiers so overlapping or manually
        # applied famine effects compound rather than overwrite each other.
        kingdom.famine_production_modifier *= (
            applied["production_modifier"]
        )

        kingdom.happiness += applied["happiness"]
        kingdom.stability += applied["stability"]

        # Percentage population effects are applied to the current population.
        # Integer conversion removes fractional citizens.
        kingdom.population = int(
            kingdom.population
            * (1 + applied["population_percent"])
        )

    elif event.event_type == "riot":
        applied = {
            # Fixed treasury damage is reduced proportionally by the response.
            "treasury": effects["treasury"] * severity,
            "happiness": effects["happiness"] * severity,
            "stability": effects["stability"] * severity,
        }

        kingdom.treasury += applied["treasury"]
        kingdom.happiness += applied["happiness"]
        kingdom.stability += applied["stability"]

    elif event.event_type == "rebellion":
        applied = {
            "population_percent": (
                effects["population_percent"] * severity
            ),
            "army_size_percent": (
                effects["army_size_percent"] * severity
            ),
            "happiness": effects["happiness"] * severity,
            "stability": effects["stability"] * severity,
        }

        # Population and army losses are proportional to their current values.
        kingdom.population = int(
            kingdom.population
            * (1 + applied["population_percent"])
        )
        kingdom.army_size = int(
            kingdom.army_size
            * (1 + applied["army_size_percent"])
        )
        kingdom.happiness += applied["happiness"]
        kingdom.stability += applied["stability"]

    elif event.event_type == "market_crash":
        applied = {
            "treasury_percent": (
                effects["treasury_percent"] * severity
            ),
            "happiness": effects["happiness"] * severity,
            "stability": effects["stability"] * severity,
        }

        # The treasury percentage is applied against current wealth, then cast
        # to int. This means a market crash removes any fractional treasury
        # amount present before the event.
        kingdom.treasury = int(
            kingdom.treasury
            * (1 + applied["treasury_percent"])
        )
        kingdom.happiness += applied["happiness"]
        kingdom.stability += applied["stability"]

    elif event.event_type == "desertion":
        applied = {
            "army_size_percent": (
                effects["army_size_percent"] * severity
            ),

            # Army quality uses a direct numerical reduction rather than a
            # percentage.
            "army_quality": effects["army_quality"] * severity,
            "stability": effects["stability"] * severity,
        }

        kingdom.army_size = int(
            kingdom.army_size
            * (1 + applied["army_size_percent"])
        )
        kingdom.army_quality += applied["army_quality"]
        kingdom.stability += applied["stability"]

    # Preserve the exact scaled values for historical reporting and comparison.
    event.applied_effects = applied

    # Save the entire Kingdom because different event types mutate different
    # groups of fields.
    kingdom.save()

    # Only applied_effects changed on Event inside this function; response text,
    # AI scores, resolution state, and timestamp were saved earlier by the view.
    event.save(update_fields=["applied_effects"])