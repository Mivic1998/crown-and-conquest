from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from datetime import timedelta
from django.utils import timezone
from .utils import next_midnight

# Create your models here.

BANNER_CHOICES = [
    ("blue", "Royal Blue"),
    ("crimson", "Crimson Empire"),
    ("emerald", "Emerald Realm"),
    ("purple", "Imperial Purple"),
    ("golden", "Golden Kingdom"),
]

CREST_CHOICES = [
    ("standard", "Standard Crown"),
    ("lion", "Crimson Lion"),
    ("dragon", "Emerald Dragon"),
    ("stag", "Imperial Stag"),
    ("eagle", "Black Eagle"),
    ("wolf", "Ice Wolf"),
]

WOLF_CREST_SCORE_REQUIREMENT = 150000


def calculate_leaderboard_score_for(kingdom):
    return int((kingdom.territory_count * 1000) + (kingdom.population * 0.1))

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
    banner_colour = models.CharField(
        max_length=20,
        choices=BANNER_CHOICES,
        default="blue",
    )

    crest = models.CharField(
        max_length=20,
        choices=CREST_CHOICES,
        default="standard",
    )

    # Population & Economy
    population = models.IntegerField(default=1000)
    treasury = models.FloatField(default=500)
    
    # Food system
    food = models.FloatField(default=1000)

    # Famine modifiers
    famine_turns_remaining = models.IntegerField(default=0)
    famine_production_modifier = models.FloatField(default=1.0)

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
    is_at_war = models.BooleanField(default=False)
    last_attacked_at = models.DateTimeField(blank=True, null=True)
    
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

    is_premium = models.BooleanField(default=False)

    stripe_customer_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    stripe_subscription_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    subscription_status = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )

    policy_advice = models.JSONField(
        default=dict,
        blank=True,
    )

    @property
    def leaderboard_score(self):
        return calculate_leaderboard_score_for(self)

    @property
    def has_wolf_crest_unlocked(self):
        return self.leaderboard_score >= WOLF_CREST_SCORE_REQUIREMENT

    @property
    def crest_image_path(self):
        crest_map = {
            "standard": "standard-crest.png",
            "lion": "lion-crest.png",
            "dragon": "dragon-crest.png",
            "stag": "stag-crest.png",
            "eagle": "eagle-crest.png",
            "wolf": "wolf-crest.png",
        }
        return f"images/crests/{crest_map.get(self.crest, 'standard-crest.png')}"

    @property
    def banner_image_path(self):
        banner_map = {
            "blue": "premium-banner-blue.png",
            "red": "premium-banner-crimson.png",
            "crimson": "premium-banner-crimson.png",
            "green": "premium-banner-emerald.png",
            "emerald": "premium-banner-emerald.png",
            "purple": "premium-banner-purple.png",
            "gold": "premium-banner-golden.png",
            "golden": "premium-banner-golden.png",
        }
        return f"images/banners/{banner_map.get(self.banner_colour, 'premium-banner-blue.png')}"

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
    population = models.IntegerField(default=1000)
    treasury = models.FloatField(default=500)
    food = models.FloatField(default=1000)

    happiness = models.FloatField(default=50)
    stability = models.FloatField(default=50)

    army_size = models.IntegerField(default=100)
    army_quality = models.FloatField(default=1.0)

    a_eff = models.FloatField(default=1.0)
    infra = models.FloatField(default=1.0)

    tax_rate = models.FloatField(default=20)
    agriculture_investment = models.FloatField(default=25)
    infrastructure_investment = models.FloatField(default=25)
    military_investment = models.FloatField(default=25)
    welfare_investment = models.FloatField(default=25)

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

    def premium_daily_limit(self):
        if self.kingdom.is_premium:
            return 6

        return 3

    def sync_with_premium_status(self):
        new_limit = self.premium_daily_limit()

        self.daily_turn_limit = new_limit

        if self.kingdom.is_premium:
            self.turns_remaining_today = max(
                self.turns_remaining_today,
                new_limit,
            )
        else:
            self.turns_remaining_today = min(
                self.turns_remaining_today,
                new_limit,
            )

        self.save(
            update_fields=[
                "daily_turn_limit",
                "turns_remaining_today",
            ]
        )

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

        self.daily_turn_limit = self.premium_daily_limit()

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

