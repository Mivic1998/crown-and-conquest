"""Core turn-processing and policy-preview logic for kingdom simulation.

This module advances a kingdom through one complete simulation turn. It
calculates changes to agriculture, infrastructure, food production,
population, treasury, military strength, happiness, and stability before
saving the updated kingdom and creating a historical turn snapshot.

The module also provides a non-persistent policy preview used by the
premium AI council advisor. That preview identifies broad areas of risk
without changing the kingdom or running the full stochastic simulation.
"""

import random

from .events import evaluate_events
from .models import Kingdom, TurnHistory


def clamp(value, minimum, maximum):
    """Restrict a numeric value to an inclusive minimum and maximum range.

    Args:
        value: The numeric value to constrain.
        minimum: The lowest permitted value.
        maximum: The highest permitted value.

    Returns:
        The original value when it falls within the range, otherwise the
        nearest boundary value.
    """
    return max(minimum, min(value, maximum))


def random_noise(stability):
    """Generate bounded random variation influenced by kingdom stability.

    Stable kingdoms experience more predictable outcomes, while unstable
    kingdoms experience greater variation. The final result is capped to
    prevent a single random roll from changing an outcome by more than 30%.

    Args:
        stability: The kingdom's current stability value from 0 to 100.

    Returns:
        A floating-point modifier between -0.3 and 0.3.
    """
    # The standard deviation grows as stability falls. At 100 stability,
    # sigma is 0.05; at 0 stability, it increases to 0.10.
    sigma = 0.05 * (1 + (100 - stability) / 100)

    # Gaussian variation makes small changes more common than extreme ones.
    noise = random.gauss(0, sigma)

    # Bounding variation prevents randomness from overpowering policy choices.
    return clamp(noise, -0.3, 0.3)


def process_turn(kingdom):
    """Advance a kingdom through one complete simulation turn.

    The calculations are performed in a fixed order because later systems
    depend on values produced earlier in the turn. The live Kingdom record is
    updated first, after which event eligibility is evaluated and a
    TurnHistory snapshot is created.

    Args:
        kingdom: The Kingdom instance belonging to the current player.

    Returns:
        A tuple containing:
            event: An Event instance when an event is generated, otherwise
                the value returned by ``evaluate_events``.
            turn: The newly created TurnHistory snapshot.

    Side effects:
        - Updates and saves the supplied Kingdom instance.
        - May generate a new Event record.
        - Creates a TurnHistory record.
    """

    # Read the player's currently selected policies once so each calculation
    # uses the same values throughout this turn.
    tax_rate = kingdom.tax_rate
    agriculture = kingdom.agriculture_investment
    infrastructure = kingdom.infrastructure_investment
    military = kingdom.military_investment
    welfare = kingdom.welfare_investment

    # ------------------------------------------------------------------
    # 1. Agricultural efficiency and infrastructure
    # ------------------------------------------------------------------

    # Agriculture provides the strongest direct improvement to agricultural
    # efficiency, while infrastructure contributes a smaller secondary boost.
    # Existing efficiency also decays by 1% each turn, requiring continued
    # investment to maintain or improve it.
    kingdom.a_eff = (
        kingdom.a_eff
        + (agriculture / 100 * 0.01)
        + (infrastructure / 100 * 0.005)
        - (kingdom.a_eff * 0.01)
    )

    # Infrastructure grows according to the current allocation but also
    # experiences 1% natural decay, rewarding sustained long-term investment.
    kingdom.infra = (
        kingdom.infra
        + (infrastructure / 100 * 0.02)
        - (kingdom.infra * 0.01)
    )

    # ------------------------------------------------------------------
    # 2. Food production
    # ------------------------------------------------------------------

    # Food output uses the stability value from the beginning of the turn.
    # Lower stability therefore makes production less predictable.
    food_noise = random_noise(kingdom.stability)

    # Agricultural efficiency determines the baseline quantity of food that
    # can be produced for the current population.
    expected_food = kingdom.population * kingdom.a_eff

    # A continuing famine can reduce output through the stored production
    # modifier, while bounded random noise introduces controlled variation.
    food_production = (
        expected_food
        * kingdom.famine_production_modifier
        * (1 + food_noise)
    )

    # Only a proportion of surplus production is retained as stored food.
    storage_rate = 0.25

    # ------------------------------------------------------------------
    # 3. Carrying capacity
    # ------------------------------------------------------------------

    # Infrastructure increases the number of people the kingdom can support
    # from the food it produces.
    carrying_capacity = food_production * (1 + kingdom.infra)

    # Prevent division by zero or extreme negative growth if production falls
    # to zero during a severe crisis.
    if carrying_capacity <= 1:
        carrying_capacity = 1

    # ------------------------------------------------------------------
    # 4. Food balance
    # ------------------------------------------------------------------

    # Each member of the population requires one unit of food during the turn.
    food_needed = kingdom.population
    food_balance = food_production - food_needed

    # ------------------------------------------------------------------
    # 5. Population growth
    # ------------------------------------------------------------------

    # Population variation is also affected by the kingdom's starting
    # stability, making unstable kingdoms less predictable.
    population_noise = random_noise(kingdom.stability)

    # Growth slows as population approaches carrying capacity. Happiness and
    # stability further determine how much of that potential growth is realised.
    growth_rate = (
        0.02
        * (1 - kingdom.population / carrying_capacity)
        * (kingdom.happiness / 100)
        * (kingdom.stability / 100)
    )

    population_change = (
        kingdom.population
        * growth_rate
        * (1 + population_noise)
    )

    # Population is stored as an integer because fractional citizens are not
    # meaningful within the simulation.
    kingdom.population += int(population_change)

    # This defensive check prevents an invalid negative population if several
    # adverse factors combine during the calculation.
    if kingdom.population < 0:
        kingdom.population = 0

    # ------------------------------------------------------------------
    # 6. Economy and treasury
    # ------------------------------------------------------------------

    economy_noise = random_noise(kingdom.stability)

    # Taxation reduces productivity non-linearly. Higher taxation therefore
    # raises the collected proportion of output while also shrinking the
    # productive economic base.
    productivity = 1 * (1 - ((tax_rate / 100) ** 2) * 0.8)

    economic_output = (
        kingdom.population
        * productivity
        * (1 + economy_noise)
    )

    revenue = economic_output * (tax_rate / 100)

    # Population and army size create recurring maintenance costs. Expanding
    # either can therefore increase long-term pressure on the treasury.
    costs = (
        kingdom.population * 0.1
        + kingdom.army_size * 0.02
    )

    kingdom.treasury += revenue - costs

    # Debt is not represented in the current simulation, so treasury cannot
    # fall below zero.
    if kingdom.treasury < 0:
        kingdom.treasury = 0

    # ------------------------------------------------------------------
    # 7. Food storage
    # ------------------------------------------------------------------

    # Only surplus production is stored. If production fails to meet current
    # demand, no food reserve remains after the turn.
    if food_balance > 0:
        kingdom.food = food_balance * storage_rate
    else:
        kingdom.food = 0

    # Defensive clamp in case future changes introduce a negative food value.
    if kingdom.food < 0:
        kingdom.food = 0

    # ------------------------------------------------------------------
    # 8. Military
    # ------------------------------------------------------------------

    # Happiness affects how effectively the current army can use its quality.
    # This strength value is calculated before recruitment, so newly recruited
    # troops contribute to stability from the following turn onward.
    army_effectiveness = (
        kingdom.army_quality
        * (kingdom.happiness / 100)
    )
    army_strength = kingdom.army_size * army_effectiveness

    # Military allocation increases army size directly. Integer conversion
    # creates threshold effects, meaning very small allocations may not add a
    # complete troop during the current turn.
    military_growth = military / 100 * 5
    kingdom.army_size += int(military_growth)

    # ------------------------------------------------------------------
    # 9. Happiness
    # ------------------------------------------------------------------

    # Happiness begins from a neutral baseline. Taxation reduces it, welfare
    # improves it, and the food balance rewards surplus or penalises shortage.
    kingdom.happiness = (
        50
        - (tax_rate * 0.3)
        + (welfare * 0.4)
        + (
            food_balance
            / max(kingdom.population, 1)
            * 2
        )
    )

    # Happiness is represented as a percentage-like value from 0 to 100.
    kingdom.happiness = clamp(kingdom.happiness, 0, 100)

    # ------------------------------------------------------------------
    # 10. Stability
    # ------------------------------------------------------------------

    # Stability depends principally on public happiness, with a smaller
    # contribution from the effective strength of the existing army.
    kingdom.stability = (
        50
        + (kingdom.happiness * 0.2)
        + (army_strength * 0.0001)
    )

    kingdom.stability = clamp(kingdom.stability, 0, 100)

    # ------------------------------------------------------------------
    # 11. Turn and famine progression
    # ------------------------------------------------------------------

    kingdom.turn_number += 1

    # Famine effects persist for a fixed number of turns. Once the counter
    # reaches zero, normal food production is restored automatically.
    if kingdom.famine_turns_remaining > 0:
        kingdom.famine_turns_remaining -= 1

    if kingdom.famine_turns_remaining == 0:
        kingdom.famine_production_modifier = 1.0

    # ------------------------------------------------------------------
    # 12. Persistence, events, and history
    # ------------------------------------------------------------------

    # Save the fully calculated live state before evaluating events so event
    # probabilities reflect the kingdom as it exists after this turn.
    kingdom.save()

    # Event evaluation uses the updated kingdom condition and may create a new
    # unresolved event that must be addressed before another turn is advanced.
    event = evaluate_events(kingdom)

    # TurnHistory has its own sequence so historical records remain ordered
    # even if it differs from the live kingdom turn counter.
    latest_turn = 1

    existing_history = TurnHistory.objects.filter(kingdom=kingdom)

    if existing_history.exists():
        latest_turn = existing_history.latest().turn_number + 1

    # Store an immutable snapshot of the completed turn. This allows reports
    # and historical statistics to remain accurate after the live Kingdom
    # continues changing.
    turn = TurnHistory.objects.create(
        kingdom=kingdom,
        turn_number=latest_turn,
        population=kingdom.population,
        treasury=kingdom.treasury,
        food=kingdom.food,
        happiness=kingdom.happiness,
        stability=kingdom.stability,
        army_size=kingdom.army_size,
        army_quality=kingdom.army_quality,
        a_eff=kingdom.a_eff,
        infra=kingdom.infra,

        # Preserve the exact policies responsible for this turn's outcome.
        tax_rate=kingdom.tax_rate,
        agriculture_investment=kingdom.agriculture_investment,
        infrastructure_investment=kingdom.infrastructure_investment,
        military_investment=kingdom.military_investment,
        welfare_investment=kingdom.welfare_investment,
    )

    return event, turn


def preview_policy_effects(kingdom, policies):
    """Estimate broad policy risks without changing persistent data.

    This function supports the premium AI council advisor by producing a
    deterministic summary of likely policy pressure. It does not attempt to
    reproduce the full turn simulation and introduces no random variation.

    Args:
        kingdom: The current Kingdom instance used to provide contextual data.
        policies: A dictionary containing proposed taxation and investment
            percentages.

    Returns:
        A dictionary describing projected pressure on treasury, food,
        happiness, stability, and military development.

    Side effects:
        None. The kingdom is not modified or saved.
    """
    tax_rate = policies["tax_rate"]
    agriculture = policies["agriculture_investment"]
    infrastructure = policies["infrastructure_investment"]
    military = policies["military_investment"]
    welfare = policies["welfare_investment"]

    # Begin from a neutral assessment and replace individual categories only
    # when the proposed policies meet a defined risk or focus threshold.
    projected = {
        "treasury_pressure": "stable",
        "food_pressure": "stable",
        "happiness_pressure": "stable",
        "stability_pressure": "stable",
        "military_pressure": "stable",
    }

    # High taxation creates a direct happiness penalty within the simulation.
    if tax_rate >= 35:
        projected["happiness_pressure"] = "high risk"
    elif tax_rate >= 25:
        projected["happiness_pressure"] = "moderate risk"

    # Low agricultural investment becomes more dangerous when the kingdom
    # already holds food reserves below half of its population requirement.
    if agriculture < 15 and kingdom.food < kingdom.population * 0.5:
        projected["food_pressure"] = "high risk"
    elif agriculture < 20:
        projected["food_pressure"] = "moderate risk"

    # Combining low welfare with elevated taxation increases the likelihood
    # that happiness and stability will come under pressure.
    if welfare < 15 and tax_rate > 25:
        projected["stability_pressure"] = "moderate risk"

    # Infrastructure provides long-term capacity rather than immediate cash,
    # so prolonged underinvestment is described as a future treasury risk.
    if infrastructure < 15:
        projected["treasury_pressure"] = "long-term risk"

    # Military thresholds communicate whether the proposed allocation strongly
    # prioritises recruitment or is unlikely to produce meaningful growth.
    if military >= 40:
        projected["military_pressure"] = "strong focus"
    elif military < 15:
        projected["military_pressure"] = "underfunded"

    return projected