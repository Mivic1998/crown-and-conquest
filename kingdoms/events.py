from .models import Kingdom
import random

def evaluate_events(kingdom):
    
    tax_rate = kingdom.tax_rate
    
    available_food = kingdom.food
    food_needed = kingdom.population
    food_balance = available_food - food_needed

    happiness = kingdom.happiness
    stability = kingdom.stability

    probabilities = {
        "famine": 0.02 + max(0, -food_balance/food_needed) * 0.5,
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







