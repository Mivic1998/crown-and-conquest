"""Persistent data models for kingdoms, turns, limits, and dynamic events.

This module defines the principal data structures used by the kingdom
simulation. Together, these models represent:

- the current mutable state of a player's kingdom;
- immutable snapshots of completed turns;
- daily turn allowances and cooldown timing;
- dynamic kingdom events and their AI-evaluated resolutions.

The live ``Kingdom`` model is updated as gameplay progresses, while
``TurnHistory`` preserves previous states for reports, statistics, charts,
and CSV export. ``TurnLimit`` separates time-based progression rules from the
main simulation data, and ``Event`` records crises generated during individual
turns.

Several properties provide derived presentation values, such as leaderboard
scores and static-image paths, without duplicating those values in the database.
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from datetime import timedelta
from django.utils import timezone
from .utils import next_midnight


# Stored choice values remain concise and database-friendly, while the second
# element in each tuple supplies the human-readable label returned by Django's
# automatically generated ``get_banner_colour_display()`` method.
BANNER_CHOICES = [
    ("blue", "Royal Blue"),
    ("crimson", "Crimson Empire"),
    ("emerald", "Emerald Realm"),
    ("purple", "Imperial Purple"),
    ("golden", "Golden Kingdom"),
]


# These choices support Django form validation and provide the display labels
# used in template alt text through ``get_crest_display()``.
CREST_CHOICES = [
    ("standard", "Standard Crown"),
    ("lion", "Crimson Lion"),
    ("dragon", "Emerald Dragon"),
    ("stag", "Imperial Stag"),
    ("eagle", "Black Eagle"),
    ("wolf", "Ice Wolf"),
]


# The wolf crest is an unlockable reward rather than an ordinary default
# customisation option. KingdomSettingsForm uses this threshold to prevent a
# player from selecting it before earning the required leaderboard score.
WOLF_CREST_SCORE_REQUIREMENT = 150000


def calculate_leaderboard_score_for(kingdom):
    """Calculate the public ranking score for a kingdom.

    Territory is weighted significantly more heavily than population, making
    successful expansion the principal contributor to leaderboard position.

    Args:
        kingdom: A Kingdom-like object with ``territory_count`` and
            ``population`` attributes.

    Returns:
        The calculated score as an integer.

    Used by:
        - ``Kingdom.leaderboard_score``;
        - dashboard and public-profile templates;
        - kingdom model tests.

    The core leaderboard view reproduces this formula using Django ORM
    expressions so the database can order all kingdoms before pagination.
    """
    return int((kingdom.territory_count * 1000) + (kingdom.population * 0.1))


class Kingdom(models.Model):
    """Represent the current mutable state of one player's kingdom.

    Each Django user can own at most one Kingdom. The model stores the current
    economic, demographic, social, military, policy, warfare, premium, and
    presentation state used throughout the application.

    Unlike ``TurnHistory``, this record is continually updated. It represents
    the kingdom as it exists now rather than preserving previous states.
    """

    # ------------------------------------------------------------------
    # Ownership
    # ------------------------------------------------------------------

    owner = models.OneToOneField(
        User,

        # Deleting the User deletes the owned Kingdom. Related records such as
        # TurnHistory, TurnLimit, Event, War, and Battle then follow their own
        # configured deletion behaviour.
        on_delete=models.CASCADE,

        # Enables reverse access as ``user.kingdom``. Views use this relationship
        # extensively to determine whether an authenticated account has entered
        # the gameplay lifecycle.
        related_name="kingdom"
    )

    # ------------------------------------------------------------------
    # Identity and presentation
    # ------------------------------------------------------------------

    # Kingdom names must be unique because they identify realms publicly and
    # are used to generate unique URL slugs during kingdom creation.
    name = models.CharField(max_length=50, unique=True)

    # The ruler name is initially populated from the owner's username and is
    # displayed in dashboards, diplomacy pages, reports, and public profiles.
    ruler_name = models.CharField(max_length=50)

    # The unique slug provides stable, readable URLs for kingdom-detail and
    # war-declaration routes.
    slug = models.SlugField(unique=True)

    banner_colour = models.CharField(
        max_length=20,

        # Choices constrain normal form submissions to supported banner assets
        # and generate ``get_banner_colour_display()`` automatically.
        choices=BANNER_CHOICES,

        # Standard kingdoms begin with the royal-blue identity.
        default="blue",
    )

    crest = models.CharField(
        max_length=20,
        choices=CREST_CHOICES,
        default="standard",
    )

    # ------------------------------------------------------------------
    # Population and economy
    # ------------------------------------------------------------------

    # These defaults establish the same initial kingdom state for each new
    # player before policy decisions and random variation begin influencing it.
    population = models.IntegerField(default=1000)
    treasury = models.FloatField(default=500)

    # ------------------------------------------------------------------
    # Food system
    # ------------------------------------------------------------------

    # Food stores the reserve remaining after the current turn's production,
    # consumption, and storage-rate calculations.
    food = models.FloatField(default=1000)

    # ------------------------------------------------------------------
    # Persistent famine modifiers
    # ------------------------------------------------------------------

    # Famine consequences may continue for multiple turns. The counter is
    # reduced by ``process_turn()`` until it reaches zero.
    famine_turns_remaining = models.IntegerField(default=0)

    # Food production is multiplied by this value during a famine. It returns
    # to 1.0 when ``famine_turns_remaining`` reaches zero.
    famine_production_modifier = models.FloatField(default=1.0)

    # ------------------------------------------------------------------
    # Core social metrics
    # ------------------------------------------------------------------

    # Both values behave like percentages and are clamped to the 0–100 range by
    # the simulation logic rather than by database-level constraints.
    happiness = models.FloatField(default=50)
    stability = models.FloatField(default=50)

    # ------------------------------------------------------------------
    # Military
    # ------------------------------------------------------------------

    # Army size represents troop quantity, while quality acts as an
    # effectiveness multiplier in diplomacy and warfare calculations.
    army_size = models.IntegerField(default=100)
    army_quality = models.FloatField(default=1.0)

    # ------------------------------------------------------------------
    # Current player policies
    # ------------------------------------------------------------------

    # Taxation affects revenue, productivity, and public happiness.
    tax_rate = models.FloatField(default=20)

    # These four investments are validated by PolicyForm to total exactly 100%.
    # Their values are stored on the live kingdom and copied into TurnHistory
    # when a turn is completed.
    agriculture_investment = models.FloatField(default=25)
    infrastructure_investment = models.FloatField(default=25)
    military_investment = models.FloatField(default=25)
    welfare_investment = models.FloatField(default=25)

    # ------------------------------------------------------------------
    # Dynamic simulation variables
    # ------------------------------------------------------------------

    # Agricultural efficiency influences expected food production and changes
    # according to agriculture, infrastructure, and natural decay.
    a_eff = models.FloatField(default=1.0)

    # Infrastructure increases carrying capacity and evolves according to
    # investment and depreciation.
    infra = models.FloatField(default=1.0)

    # ------------------------------------------------------------------
    # Turn system
    # ------------------------------------------------------------------

    # The live turn number advances whenever ``process_turn()`` completes.
    turn_number = models.IntegerField(default=1)

    # This field belongs to an earlier/simple turn representation. The current
    # application reads progression availability from the related TurnLimit
    # model instead.
    turns_remaining = models.IntegerField(default=3)

    # ------------------------------------------------------------------
    # Warfare state
    # ------------------------------------------------------------------

    # Momentum and prestige are hidden strategic values. War simulation converts
    # them into bounded combat modifiers and updates them after each result.
    battle_momentum = models.FloatField(default=0.0)
    prestige = models.FloatField(default=0.0)

    # Stored totals allow templates and simulations to access a kingdom's record
    # directly without recounting all historical wars on each request.
    wars_won = models.PositiveIntegerField(default=0)
    wars_lost = models.PositiveIntegerField(default=0)

    # This denormalised flag supports fast checks throughout the diplomacy and
    # dashboard workflows. War records preserve the full relationship history.
    is_at_war = models.BooleanField(default=False)

    # Used to prevent a defender from being repeatedly attacked by different
    # kingdoms within the global two-hour protection period.
    last_attacked_at = models.DateTimeField(blank=True, null=True)

    # Territory is the strongest component of leaderboard score and may move
    # between kingdoms following warfare.
    territory_count = models.IntegerField(default=50)

    # ------------------------------------------------------------------
    # Activity metadata
    # ------------------------------------------------------------------

    # ``blank=True`` permits omission in forms; ``null=True`` represents the
    # absence of a timestamp in the database before the first refresh.
    last_active_at = models.DateTimeField(blank=True, null=True)

    # Set once when the kingdom is created.
    created_at = models.DateTimeField(auto_now_add=True)

    # Updated automatically whenever ``save()`` performs a normal model save.
    updated_at = models.DateTimeField(auto_now=True)

    # ------------------------------------------------------------------
    # War availability
    # ------------------------------------------------------------------

    # A kingdom is available as a diplomacy target only while this timestamp is
    # present and remains later than the current server time.
    war_available_until = models.DateTimeField(
        blank=True,
        null=True
    )

    # ------------------------------------------------------------------
    # Premium and Stripe state
    # ------------------------------------------------------------------

    # This Boolean is the application-wide entitlement check used by templates,
    # policy advice, statistics, CSV export, settings, and turn limits.
    is_premium = models.BooleanField(default=False)

    # Stripe identifiers are nullable because a standard kingdom has never
    # created a Stripe customer or subscription.
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

    # The exact lifecycle status supplied by Stripe is stored for
    # synchronisation and inspection. An empty string represents no subscription.
    subscription_status = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )

    # Premium council advice is structured as JSON containing values such as
    # ``summary``, ``risk``, and ``recommendation``. ``default=dict`` creates a
    # new dictionary for each model instance rather than sharing one mutable
    # default between kingdoms.
    policy_advice = models.JSONField(
        default=dict,
        blank=True,
    )

    @property
    def leaderboard_score(self):
        """Return the kingdom's current territory-and-population score.

        This value is derived rather than stored, preventing it from becoming
        stale whenever territory or population changes.

        Read by:
            - dashboard;
            - leaderboard-related presentation;
            - public kingdom detail;
            - crest-unlock logic;
            - model tests.
        """
        return calculate_leaderboard_score_for(self)

    @property
    def has_wolf_crest_unlocked(self):
        """Return whether the kingdom has earned the wolf crest.

        KingdomSettingsForm uses this property to limit the wolf option until
        the leaderboard threshold is reached.
        """
        return self.leaderboard_score >= WOLF_CREST_SCORE_REQUIREMENT

    @property
    def crest_image_path(self):
        """Return the static-file path for the kingdom's selected crest.

        The value is calculated from the stored choice rather than storing the
        full asset path in the database. Unknown values safely fall back to the
        standard crest.

        Templates pass this path into Django's ``static`` template tag.
        """
        crest_map = {
            "standard": "standard-crest.png",
            "lion": "lion-crest.png",
            "dragon": "dragon-crest.png",
            "stag": "stag-crest.png",
            "eagle": "eagle-crest.png",
            "wolf": "wolf-crest.png",
        }
        return f"images/crests/{crest_map.get(self.crest, 'standard-crest.png')}" #Creates image path for crest so that when dashboard template is loaded, the relevant crest appears.

    @property
    def banner_image_path(self):
        """Return the static-file path for the selected premium banner.

        Both current choice keys and several legacy/alternate colour keys map
        to the available image filenames. Unknown values fall back to blue.

        Dashboard and settings templates use this property to construct their
        background-image URLs.
        """
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
        """Mark the kingdom active and extend its attackable window.

        Args:
            hours: Number of hours for which the kingdom remains available as a
                diplomacy target. Defaults to six.

        Side effects:
            - Updates ``last_active_at``;
            - updates ``war_available_until``;
            - immediately saves those fields.

        Called from:
            Kingdom dashboard, turn/event reports, settings, and statistics
            views, keeping active players visible to the diplomacy system.
        """
        now = timezone.now()

        self.last_active_at = now
        self.war_available_until = now + timedelta(hours=hours)

        # ``update_fields`` limits the SQL update to the timestamps modified by
        # this method.
        self.save(update_fields=[
            "last_active_at",
            "war_available_until",
        ])

    def is_available_for_war(self):
        """Return whether the current war-availability window is active.

        This performs no database write. It is used by premium policy-advice
        fallback logic when assessing military underinvestment.
        """
        return (
            self.war_available_until is not None
            and self.war_available_until > timezone.now()
        )

    def __str__(self):
        """Return the kingdom name for admin pages and debugging output."""
        return self.name


class TurnHistory(models.Model):
    """Store an immutable-style snapshot of one completed kingdom turn.

    The live Kingdom continues changing, so reports and charts cannot rely on
    it to reconstruct previous states. Each TurnHistory row records the metrics
    and policy values that existed when a particular turn completed.
    """

    kingdom = models.ForeignKey(
        Kingdom,

        # Deleting a kingdom removes all of its historical snapshots because
        # they have no meaningful owner-independent use.
        on_delete=models.CASCADE,

        # Enables reverse access as ``kingdom.history``. Views use this for
        # dashboard notifications, reports, charts, comparisons, and CSV export.
        related_name="history"
    )

    # This sequence is maintained by ``process_turn()`` independently of the
    # database primary key.
    turn_number = models.IntegerField()

    # This optional textual field can associate an event type directly with a
    # snapshot. The principal event relationship is the reverse one-to-one
    # ``turn.event`` created by Event.turn.
    event_type = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    # ------------------------------------------------------------------
    # Snapshot of key simulation values
    # ------------------------------------------------------------------

    population = models.IntegerField(default=1000)
    treasury = models.FloatField(default=500)
    food = models.FloatField(default=1000)

    happiness = models.FloatField(default=50)
    stability = models.FloatField(default=50)

    army_size = models.IntegerField(default=100)
    army_quality = models.FloatField(default=1.0)

    a_eff = models.FloatField(default=1.0)
    infra = models.FloatField(default=1.0)

    # Preserve the exact policy allocation responsible for this turn so future
    # reports remain accurate even after the live Kingdom policies change.
    tax_rate = models.FloatField(default=20)
    agriculture_investment = models.FloatField(default=25)
    infrastructure_investment = models.FloatField(default=25)
    military_investment = models.FloatField(default=25)
    welfare_investment = models.FloatField(default=25)

    # Dashboard notifications query snapshots where this remains False. Opening
    # the turn-detail page changes it to True.
    report_seen = models.BooleanField(default=False)

    # Records when the historical snapshot was first created.
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Define default historical ordering and Django's latest lookup field."""

        # Queries without explicit ordering return oldest turn first.
        ordering = ["turn_number"]

        # Enables ``queryset.latest()`` without specifying a field each time.
        get_latest_by = "turn_number"

    def __str__(self):
        """Return a readable kingdom-and-turn label."""
        return f"{self.kingdom.name} - Turn {self.turn_number}"


class TurnLimit(models.Model):
    """Store daily turn allowances, resets, and between-turn cooldowns.

    Separating this state from Kingdom keeps time-based progression rules
    independent from the economic and military simulation. Each kingdom has
    exactly one TurnLimit record created during kingdom creation.
    """

    kingdom = models.OneToOneField(
        Kingdom,

        # A turn allowance cannot exist without its kingdom.
        on_delete=models.CASCADE,

        # Enables reverse access as ``kingdom.turn_limit`` throughout dashboard,
        # simulation, payment, and test code.
        related_name="turn_limit"
    )

    # Standard kingdoms receive three turns; premium synchronisation changes
    # this to six where appropriate.
    daily_turn_limit = models.IntegerField(
        default=3
    )

    # This is the mutable allowance consumed during the current daily period.
    turns_remaining_today = models.IntegerField(
        default=3
    )

    # The waiting period between successive turns is stored as data so the rule
    # can be changed without rewriting ``use_turn()``.
    cooldown_minutes = models.IntegerField(
        default=120
    )

    # Nullable because a newly created kingdom has not yet taken a turn and
    # therefore has no active or historic cooldown end.
    cooldown_ends_at = models.DateTimeField(
        blank=True,
        null=True
    )

    # The next timestamp at which the daily allowance should be replenished.
    daily_reset_at = models.DateTimeField()

    # Nullable until the first turn is processed.
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
        """Return a readable label for admin and debugging output."""
        return f"Turn limit for {self.kingdom.name}"

    def premium_daily_limit(self):
        """Return the allowance appropriate to the kingdom's premium state."""
        if self.kingdom.is_premium:
            return 6

        return 3

    def sync_with_premium_status(self):
        """Synchronise turn allowance after a premium-status change.

        Premium activation raises remaining turns to at least six. Premium
        removal reduces any remaining allowance to at most three.

        Side effects:
            Updates and saves ``daily_turn_limit`` and
            ``turns_remaining_today``.

        Called from:
            Payment webhook utility logic after subscription activation,
            cancellation, or status updates.
        """
        new_limit = self.premium_daily_limit()

        self.daily_turn_limit = new_limit

        if self.kingdom.is_premium:
            # Upgrading immediately grants the full premium allowance even when
            # some standard turns were already consumed.
            self.turns_remaining_today = max(
                self.turns_remaining_today,
                new_limit,
            )
        else:
            # Downgrading prevents a former premium user from retaining more
            # turns than the standard daily maximum.
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
        """Return whether the stored between-turn cooldown is still active."""
        return (
            self.cooldown_ends_at is not None
            and self.cooldown_ends_at > timezone.now()
        )

    def has_turns_remaining(self):
        """Return whether at least one daily turn remains."""
        return self.turns_remaining_today > 0

    def can_take_turn(self):
        """Return whether both allowance and cooldown rules permit a turn."""
        return (
            self.has_turns_remaining()
            and not self.cooldown_active()
        )

    def refresh_daily_turns(self):
        """Update the limit for premium status and reset it when due.

        The current premium-based limit is recalculated on every call. If the
        reset timestamp has passed, the daily allowance is replenished and the
        next reset is calculated by ``next_midnight()``.

        Side effects:
            Saves the TurnLimit record.
        """
        now = timezone.now()

        # Keep the configured limit aligned with the current entitlement even if
        # this method is reached independently of a payment webhook.
        self.daily_turn_limit = self.premium_daily_limit()

        if now >= self.daily_reset_at:
            self.turns_remaining_today = self.daily_turn_limit
            self.daily_reset_at = next_midnight()

        self.save()

    def use_turn(self):
        """Consume one turn and begin the configured cooldown.

        The view checks ``can_take_turn()`` before calling this method. This
        method itself performs the state transition without repeating that
        validation.

        Side effects:
            - Decrements ``turns_remaining_today``;
            - records ``last_turn_taken_at``;
            - sets ``cooldown_ends_at``;
            - saves the model.
        """
        now = timezone.now()

        self.turns_remaining_today -= 1
        self.last_turn_taken_at = now
        self.cooldown_ends_at = now + timedelta(
            minutes=self.cooldown_minutes
        )

        self.save()


class Event(models.Model):
    """Record a dynamic crisis and the player's AI-evaluated response.

    An Event belongs to one kingdom and can be linked one-to-one with the exact
    TurnHistory snapshot that generated it. Before resolution it stores the
    scenario; afterwards it also stores the player's decree, individual AI
    category scores, combined score, feedback, and effects applied to the
    kingdom.
    """

    EVENT_TYPES = [
        ("famine", "Famine"),
        ("riot", "Riot"),
        ("rebellion", "Rebellion"),
        ("market_crash", "Market Crash"),
        ("desertion", "Desertion"),
    ]

    kingdom = models.ForeignKey(
        Kingdom,

        # Deleting the kingdom removes all events associated with its gameplay
        # history.
        on_delete=models.CASCADE,

        # Enables ``kingdom.events`` for unresolved-event checks, notification
        # queries, event history, and ownership filtering.
        related_name="events"
    )

    turn = models.OneToOneField(
        TurnHistory,

        # Deleting the associated historical snapshot also deletes the event.
        on_delete=models.CASCADE,

        # Enables reverse access as ``turn.event`` in turn-feedback, history,
        # detail, and report templates.
        related_name="event",

        # Nullability supports records created without a historical link,
        # including legacy or manually created Event objects.
        null=True,
        blank=True
    )

    # Duplicating the turn number allows event history to be ordered and
    # displayed directly without always traversing the optional turn relation.
    turn_number = models.IntegerField()

    # Choices validate supported crisis types and generate
    # ``get_event_type_display()`` for templates.
    event_type = models.CharField(
        max_length=50,
        choices=EVENT_TYPES
    )

    # Narrative text selected from EVENT_EFFECTS when the record is created.
    description = models.TextField(blank=True)

    # Stores the exact scaled consequences applied after AI evaluation. Event
    # reports compare this dictionary with the original predefined effects.
    applied_effects = models.JSONField(
        default=dict,
        blank=True
    )

    # ------------------------------------------------------------------
    # Player response and report lifecycle
    # ------------------------------------------------------------------

    # An unresolved event blocks further turns until the player submits a
    # decree and its effects are applied.
    is_resolved = models.BooleanField(default=False)

    # Dashboard notifications remain active until the event-detail page marks
    # the completed report as seen.
    report_seen = models.BooleanField(default=False)

    # These fields remain null until the player completes the response workflow.
    # ``blank=True`` also permits omission through Django forms or admin.
    player_response = models.TextField(blank=True, null=True)
    empathy = models.FloatField(blank=True, null=True)
    practicality = models.FloatField(blank=True, null=True)
    leadership = models.FloatField(blank=True, null=True)

    # The backend calculates this combined score from the individual AI
    # categories rather than accepting a final total directly from Gemini.
    ai_score = models.FloatField(blank=True, null=True)

    ai_feedback = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    # Remains null while the crisis is unresolved and is set to server time when
    # the response workflow completes.
    resolved_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        """Define chronological ordering and latest-event lookup behaviour."""

        ordering = ["turn_number"]
        get_latest_by = "turn_number"

    def __str__(self):
        """Return a readable kingdom, event-type, and turn label."""
        return f"{self.kingdom.name} - {self.event_type} - Turn {self.turn_number}"