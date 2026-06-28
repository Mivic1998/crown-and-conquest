from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify

# Create your models here.

class Kingdom(models.Model):
    # Ownership
    owner = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="kingdom"
    )

    # Identity
    name = models.CharField(max_length=50, unique=True)
    ruler_name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)

    # Population & Economy
    population = models.IntegerField(default=1000)
    treasury = models.FloatField(default=500)
    
    # Food system
    food = models.FloatField(default=1000)

    # Famine modifiers
    famine_turns_remaining = models.IntegerField(default=0)
    food_production_modifier = models.FloatField(default=1.0)

    # Core metrics
    happiness = models.FloatField(default=50)
    stability = models.FloatField(default=50)

    # Military
    army_size = models.IntegerField(default=100)
    army_quality = models.FloatField(default=1.0)

    # --- POLICY (current player decisions) ---
    tax_rate = models.FloatField(default=20)

    agriculture_investment = models.FloatField(default=25)
    infrastructure_investment = models.FloatField(default=25)
    military_investment = models.FloatField(default=25)
    welfare_investment = models.FloatField(default=25)

    # --- DYNAMIC SYSTEM VARIABLES ---
    a_eff = models.FloatField(default=1.0)   # agricultural efficiency
    infra = models.FloatField(default=1.0)   # infrastructure level

    # Turn system
    turn_number = models.IntegerField(default=1)

    territory_count = models.IntegerField(default = 50)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class TurnHistory(models.Model):
    kingdom = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="history"
    )

    turn_number = models.IntegerField()

    # Snapshot of key values
    population = models.IntegerField()
    treasury = models.FloatField()
    food = models.FloatField()

    happiness = models.FloatField()
    stability = models.FloatField()

    army_size = models.IntegerField()
    army_quality = models.FloatField()

    a_eff = models.FloatField()
    infra = models.FloatField()

    tax_rate = models.FloatField()

    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["turn_number"]
        get_latest_by = "turn_number"

    def __str__(self):
        return f"{self.kingdom.name} - Turn {self.turn_number}"
    
class Event(models.Model):

    EVENT_TYPES = [
        ("famine", "Famine"),
        ("riot", "Riot"),
        ("rebellion", "Rebellion"),
        ("market_crash", "Market Crash"),
        ("desertion", "Desertion"),
    ]

    kingdom = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="events"
    )

    turn = models.OneToOneField(
        TurnHistory,
        on_delete=models.CASCADE,
        related_name="event",
        null=True,
        blank=True
    )

    turn_number = models.IntegerField()

    event_type = models.CharField(
        max_length=50,
        choices=EVENT_TYPES
    )

    description = models.TextField(blank=True)

    # Immediate effects already applied
    population_change = models.IntegerField(default=0)
    treasury_change = models.FloatField(default=0)
    food_change = models.FloatField(default=0)
    army_size_change = models.IntegerField(default=0)
    army_quality_change = models.FloatField(default=0)
    happiness_change = models.FloatField(default=0)
    stability_change = models.FloatField(default=0)

    # Ongoing modifiers
    duration_turns = models.IntegerField(default=0)
    food_production_modifier = models.FloatField(default=1.0)
    tax_income_modifier = models.FloatField(default=1.0)

    # Player response flow
    is_resolved = models.BooleanField(default=False)
    player_response = models.TextField(blank=True, null=True)
    ai_score = models.FloatField(blank=True, null=True)
    ai_feedback = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.kingdom.name} - {self.event_type} - Turn {self.turn_number}"

class AIResponse(models.Model):
    event = models.OneToOneField(
        Event,
        on_delete=models.CASCADE,
        related_name="response"
    )

    player_input = models.TextField()

    empathy = models.FloatField()
    practicality = models.FloatField()
    leadership = models.FloatField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"AI Response - {self.event.event_type}"
    
