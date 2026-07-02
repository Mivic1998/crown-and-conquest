from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from datetime import timedelta
from django.utils import timezone
from .utils import next_midnight

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
    turns_remaining = models.IntegerField(default=3)

    # kingdoms/models.py

    battle_momentum = models.FloatField(default=0.0)
    prestige = models.FloatField(default=0.0)
    wars_won = models.PositiveIntegerField(default=0)
    wars_lost = models.PositiveIntegerField(default=0)

    territory_count = models.IntegerField(default = 50)

    # Metadata
    last_active_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # War availability
    war_available_until = models.DateTimeField(
        blank=True,
        null=True
    )

    def refresh_war_availability(self, hours=6):
        now = timezone.now()

        self.last_active_at = now
        self.war_available_until = now + timedelta(hours=hours)

        self.save(update_fields=[
            "last_active_at",
            "war_available_until",
        ])


    def is_available_for_war(self):
        return (
            self.war_available_until is not None
            and self.war_available_until > timezone.now()
        )
   
    def __str__(self):
        return self.name


class TurnHistory(models.Model):
    kingdom = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="history"
    )

    turn_number = models.IntegerField()

    event_type = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )   

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

    report_seen = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["turn_number"]
        get_latest_by = "turn_number"

    def __str__(self):
        return f"{self.kingdom.name} - Turn {self.turn_number}"
    

class TurnLimit(models.Model):

    kingdom = models.OneToOneField(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="turn_limit"
    )

    daily_turn_limit = models.IntegerField(
        default=3
    )

    turns_remaining_today = models.IntegerField(
        default=3
    )

    cooldown_minutes = models.IntegerField(
        default=120
    )

    cooldown_ends_at = models.DateTimeField(
        blank=True,
        null=True
    )

    daily_reset_at = models.DateTimeField()

    last_turn_taken_at = models.DateTimeField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"Turn limit for {self.kingdom.name}"

    def cooldown_active(self):
        return (
            self.cooldown_ends_at is not None
            and self.cooldown_ends_at > timezone.now()
        )

    def has_turns_remaining(self):
        return self.turns_remaining_today > 0

    def can_take_turn(self):
        return (
            self.has_turns_remaining()
            and not self.cooldown_active()
        )
    
    def refresh_daily_turns(self):
        now = timezone.now()

        if now >= self.daily_reset_at:
            self.turns_remaining_today = self.daily_turn_limit
            self.daily_reset_at = next_midnight()
            self.save()

    def use_turn(self):
        now = timezone.now()

        self.turns_remaining_today -= 1
        self.last_turn_taken_at = now
        self.cooldown_ends_at = now + timedelta(
            minutes=self.cooldown_minutes
        )

        self.save()

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

    applied_effects = models.JSONField(
        default=dict,
        blank=True
    )

    # Player response flow
    is_resolved = models.BooleanField(default=False)
    report_seen = models.BooleanField(default=False)
    player_response = models.TextField(blank=True, null=True)
    empathy = models.FloatField(blank=True, null=True)
    practicality = models.FloatField(blank=True, null=True)
    leadership = models.FloatField(blank=True, null=True)
    ai_score = models.FloatField(blank=True, null=True)
    ai_feedback = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["turn_number"]
        get_latest_by = "turn_number"

    def __str__(self):
        return f"{self.kingdom.name} - {self.event_type} - Turn {self.turn_number}"

