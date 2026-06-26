from models import Kingdom, TurnHistory
import random

def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum)) # Ensures that metrics stay within the range [minimum, maximum]

def random_noise(stability):
    sigma = 0.05 * (1 + (100 - stability) / 100)
    noise = random.gauss(0, sigma)
    return clamp(noise, -0.3, 0.3) # Prevents 

def process_turn(kingdom):

    # Player inputs
    tax_rate = kingdom.tax_rate
    A = kingdom.agriculture_investment
    I = kingdom.infrastructure_investment
    M = kingdom.military_investment
    W = kingdom.welfare_investment

    # 1. Update efficiencies
    kingdom.a_eff = kingdom.a_eff + (A / 100 * 0.01) + (I / 100 * 0.005) - (kingdom.a_eff * 0.01)
    kingdom.infra = kingdom.infra + (I / 100 * 0.02) - (kingdom.infra * 0.01)

    # 2. Food production
    food_noise = random_noise(kingdom.stability)
    expected_food = kingdom.population * kingdom.a_eff
    food_production = expected_food * (1 + food_noise)
    storage_rate = 0.25

    # 3. Carrying capacity
    carrying_capacity = food_production * (1 + kingdom.infra)

    if carrying_capacity <= 1:
        carrying_capacity = 1

    # 4. Food balance
    food_needed = kingdom.population
    food_balance = food_production - food_needed

    # 5. Population growth
    pop_noise = random_noise(kingdom.stability)

    growth_rate = (
        0.02
        * (1 - kingdom.population / carrying_capacity)
        * (kingdom.happiness / 100)
        * (kingdom.stability / 100)
    )

    population_change = kingdom.population * growth_rate * (1 + pop_noise)
    kingdom.population += int(population_change)

    if kingdom.population < 0:
        kingdom.population = 0

    # 6. Economy
    econ_noise = random_noise(kingdom.stability)

    productivity = 1 * (1 - ((tax_rate / 100) ** 2) * 0.8)
    economic_output = kingdom.population * productivity * (1 + econ_noise)
    revenue = economic_output * (tax_rate / 100)

    costs = kingdom.population * 0.1 + kingdom.army_size * 0.02

    kingdom.treasury += revenue - costs

    if kingdom.treasury < 0:
        kingdom.treasury = 0

    # 7. Food storage
    if food_balance > 0:
        kingdom.food = food_balance * storage_rate
    else:
        kingdom.food = 0

    if kingdom.food < 0:
        kingdom.food = 0

    # 8. Military
    army_effectiveness = kingdom.army_quality * (kingdom.happiness / 100)
    army_strength = kingdom.army_size * army_effectiveness

    military_growth = M / 100 * 5
    kingdom.army_size += int(military_growth)

    # 9. Happiness
    kingdom.happiness = (
        50
        - (tax_rate * 0.3)
        + (W * 0.4)
        + (food_balance / max(kingdom.population, 1) * 2)
    )

    kingdom.happiness = clamp(kingdom.happiness, 0, 100)

    # 10. Stability
    kingdom.stability = (
        50
        + (kingdom.happiness * 0.2)
        + (army_strength * 0.0001)
    )

    kingdom.stability = clamp(kingdom.stability, 0, 100)

    # 11. Advance turn
    kingdom.turn_number += 1

    # 12. Save updated kingdom
    kingdom.save()

    latest_turn = TurnHistory.objects.latest()

    TurnHistory.objects.create(
        kingdom=kingdom,
        turn_number=latest_turn + 1,
        population=kingdom.population,
        treasury=kingdom.treasury,
        food=kingdom.food,
        happiness=kingdom.happiness,
        stability=kingdom.stability,
        army_size=kingdom.army_size,
        army_quality = kingdom.army_quality,
        a_eff = kingdom.a_eff,
        infra = kingdom.infra,

        # Policy settings used this turn
        tax_rate=kingdom.tax_rate,
        agriculture_investment=kingdom.agriculture_investment,
        infrastructure_investment=kingdom.infrastructure_investment,
        military_investment=kingdom.military_investment,
        welfare_investment=kingdom.welfare_investment,
    )

    return kingdom



