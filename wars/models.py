"""Persistent warfare models for declarations, battles, and cooldowns.

This module defines the database structures used to represent the complete
lifecycle of warfare within Crown & Conquest.

The models separate three related concerns:

- ``War`` stores the declaration, participants, rallying cries, AI evaluations,
  response deadline, status, and eventual winner.
- ``Battle`` stores the immutable-style result produced when a War is resolved,
  including hidden modifiers, final strengths, losses, and narrative output.
- ``WarCooldown`` stores directional attacker-to-defender restrictions that
  prevent the same kingdom pairing from immediately entering another conflict.

The detailed battle calculations are performed in ``wars.simulation``. These
models preserve the inputs and outputs of that calculation so views and
templates can display an explainable historical record.
"""

from datetime import timedelta

from django.db import models
from django.utils import timezone

from kingdoms.models import Kingdom


class War(models.Model):
    """Represent one conflict between an attacking and defending kingdom.

    A War begins in ``pending_defender`` state after the attacker submits a
    rallying cry. The defender then has a three-hour response window. Once the
    battle simulation completes, the War is marked ``resolved`` and linked to
    exactly one Battle through the reverse ``battle`` relationship.

    Both rallying cries and their structured Gemini evaluations are stored on
    this model. This preserves the precise qualitative input used by the battle
    simulation and allows the completed report to explain each side's result.
    """

    # Restrict persisted status values to the two states supported by the
    # current warfare workflow. Django also creates ``get_status_display()``.
    STATUS_CHOICES = [
        ("pending_defender", "Pending Defender Response"),
        ("resolved", "Resolved"),
    ]

    attacker = models.ForeignKey(
        Kingdom,

        # A war cannot remain meaningful if its attacking kingdom is deleted.
        # Deleting the attacker therefore deletes the War and its related Battle.
        on_delete=models.CASCADE,

        # Enables forward access as ``war.attacker`` and reverse access as
        # ``kingdom.wars_started``. Dashboard and history views use this reverse
        # relationship to retrieve conflicts initiated by a kingdom.
        related_name="wars_started",
    )

    defender = models.ForeignKey(
        Kingdom,

        # Deleting the defending kingdom also removes the War because the
        # conflict no longer has both required participants.
        on_delete=models.CASCADE,

        # Enables ``war.defender`` and ``kingdom.wars_received``. The dashboard,
        # defender-notification view, and war-history page use the reverse name.
        related_name="wars_received",
    )

    status = models.CharField(
        max_length=30,

        # Form and model validation accept only the supported lifecycle states.
        choices=STATUS_CHOICES,

        # A new declaration always begins by awaiting the defender.
        default="pending_defender",
    )

    # Set once by Django when the declaration is first created. The default
    # model ordering uses this value to show the newest wars first.
    declared_at = models.DateTimeField(
        auto_now_add=True
    )

    # ``blank=True`` permits omission during Django validation and ``null=True``
    # permits SQL NULL. ``save()`` supplies a three-hour deadline when this
    # value has not already been provided.
    defender_response_deadline = models.DateTimeField(
        blank=True,
        null=True
    )

    # Remains absent while the war is pending and is set by
    # ``resolve_war_simulation()`` when the conflict finishes.
    resolved_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    winner = models.ForeignKey(
        Kingdom,

        # SET_NULL preserves the historical War if the winning Kingdom is later
        # deleted. The surviving record then indicates that a winner once
        # existed but no longer has a corresponding Kingdom row.
        on_delete=models.SET_NULL,

        # Draws have no winner, and pending wars have not yet determined one.
        null=True,
        blank=True,

        # Enables ``kingdom.wars_won_records`` for retrieving the War rows in
        # which that kingdom was recorded as winner.
        related_name="wars_won_records",
    )

    # ------------------------------------------------------------------
    # Attacker rallying cry and Gemini evaluation
    # ------------------------------------------------------------------

    # The attacker's submitted speech is validated by WarForm and written when
    # ``declare_war()`` creates the War. ``blank=True`` permits empty values for
    # administrative, test, or legacy records.
    attacker_rallying_cry = models.TextField(blank=True)

    # Gemini evaluates the rallying cry across three individual categories.
    # Defaults of zero allow the model to exist before an evaluation is stored.
    attacker_leadership_score = models.FloatField(default=0)
    attacker_inspiration_score = models.FloatField(default=0)
    attacker_practicality_score = models.FloatField(default=0)

    # The AI helper converts the category average into a narrow, bounded combat
    # multiplier. A neutral default of 1.0 has no effect on battle strength.
    attacker_rally_modifier = models.FloatField(default=1.0)

    # Stored feedback is presented in the completed battle report.
    attacker_ai_feedback = models.TextField(
        blank=True
    )

    # ------------------------------------------------------------------
    # Defender rallying cry and Gemini evaluation
    # ------------------------------------------------------------------

    # This remains blank until the defender answers. If the response deadline
    # passes without an answer, the simulation replaces it with a default
    # explanatory message.
    defender_rallying_cry = models.TextField(
        blank=True
    )

    defender_leadership_score = models.FloatField(default=0)
    defender_inspiration_score = models.FloatField(default=0)
    defender_practicality_score = models.FloatField(default=0)

    # The neutral value is replaced by either the defender's evaluated modifier
    # or the conservative timeout modifier used during automatic resolution.
    defender_rally_modifier = models.FloatField(default=1.0)

    defender_ai_feedback = models.TextField(
        blank=True
    )

    # Records whether battle resolution occurred without a defender rallying
    # cry. The battle-report template uses this to explain that the defending
    # ruler failed to respond before the deadline.
    defender_auto_resolved = models.BooleanField(
        default=False
    )

    class Meta:
        """Define the default order in which War records are returned."""

        # War-history querysets show recent declarations before older ones
        # unless a view explicitly requests different ordering.
        ordering = ["-declared_at"]

    def save(self, *args, **kwargs):
        """Ensure every newly saved War has a defender-response deadline.

        When no deadline is supplied, it is calculated as three hours from the
        current server time. Explicit deadlines remain unchanged, supporting
        tests and controlled administrative creation.

        Args:
            *args: Positional arguments forwarded to ``models.Model.save``.
            **kwargs: Keyword arguments forwarded to ``models.Model.save``.

        Side effects:
            May assign ``defender_response_deadline`` before saving the model.
        """
        # The falsy check covers both None and other empty values. The normal
        # declaration view supplies its own equivalent three-hour timestamp,
        # while this method provides a model-level fallback for every other
        # creation path.
        if not self.defender_response_deadline:
            self.defender_response_deadline = (
                timezone.now() + timedelta(hours=3)
            )

        super().save(*args, **kwargs)

    @property
    def has_expired(self):
        """Return whether the unresolved defender-response period has ended.

        A past deadline alone is not enough: resolved wars deliberately return
        False so completed conflicts are not treated as expired pending wars.

        Read by:
            ``war_pending()`` to trigger automatic resolution after timeout.

        Returns:
            True when the War is still pending and the current server time is
            at or beyond the response deadline; otherwise False.
        """
        return (
            self.status == "pending_defender"
            and timezone.now() >= self.defender_response_deadline
        )

    def __str__(self):
        """Return a readable attacker-versus-defender label."""
        return f"{self.attacker.name} vs {self.defender.name}"


class Battle(models.Model):
    """Store the final calculated result of one resolved War.

    A Battle is created by ``resolve_war_simulation()`` after all combat inputs
    have been evaluated. It preserves hidden momentum, prestige, and random
    modifiers alongside the final strengths and visible outcome.

    The model acts as a historical result record. Current Kingdom army sizes,
    momentum, prestige, territory, and war statistics continue to change, while
    the Battle retains the values used when this specific conflict was resolved.
    """

    # These values define the three outcomes supported by the simulation and
    # generate ``get_outcome_display()`` for readable admin/debug output.
    OUTCOME_CHOICES = [
        ("attacker_victory", "Attacker Victory"),
        ("defender_victory", "Defender Victory"),
        ("draw", "Draw"),
    ]

    war = models.OneToOneField(
        War,

        # Deleting the parent War deletes its result because the Battle has no
        # independent context without the declaration and participants.
        on_delete=models.CASCADE,

        # Enables forward access as ``battle.war`` and reverse access as
        # ``war.battle``. Views and tests use the reverse relationship to open
        # the report associated with a resolved War.
        related_name="battle",
    )

    attacker = models.ForeignKey(
        Kingdom,

        # Deleting the attacker deletes the Battle, even though deleting the
        # same kingdom also deletes the parent War through War.attacker.
        on_delete=models.CASCADE,

        # Enables ``kingdom.attacking_battles`` for battles in which the kingdom
        # occupied the attacking role.
        related_name="attacking_battles",
    )

    defender = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,

        # Enables ``kingdom.defending_battles`` for battles in which the kingdom
        # occupied the defending role.
        related_name="defending_battles",
    )

    # ------------------------------------------------------------------
    # Hidden modifiers used during resolution
    # ------------------------------------------------------------------

    # Momentum modifiers are derived from each Kingdom's battle_momentum and
    # clamped by the warfare simulation. A default of 1.0 is neutral.
    attacker_momentum_modifier = models.FloatField(
        default=1.0
    )

    defender_momentum_modifier = models.FloatField(
        default=1.0
    )

    # Prestige modifiers are derived independently and stored so the completed
    # calculation remains auditable even after live prestige values change.
    attacker_prestige_modifier = models.FloatField(
        default=1.0
    )

    defender_prestige_modifier = models.FloatField(
        default=1.0
    )

    # The simulation generates a bounded random factor from 0.95 to 1.05 for
    # each side. Persisting it makes the otherwise stochastic outcome traceable.
    attacker_random_factor = models.FloatField(
        default=1.0
    )

    defender_random_factor = models.FloatField(
        default=1.0
    )

    # ------------------------------------------------------------------
    # Final calculated strengths
    # ------------------------------------------------------------------

    # These values store the complete post-modifier combat strengths rather
    # than recalculating them from kingdoms whose armies may later change.
    attacker_strength = models.FloatField(default=0)

    defender_strength = models.FloatField(default=0)

    # ------------------------------------------------------------------
    # Visible battle results
    # ------------------------------------------------------------------

    outcome = models.CharField(
        max_length=30,
        choices=OUTCOME_CHOICES,
    )

    # PositiveIntegerField prevents negative casualty counts at the model field
    # level. The battle simulation also calculates losses as non-negative values.
    attacker_losses = models.PositiveIntegerField(
        default=0
    )

    defender_losses = models.PositiveIntegerField(
        default=0
    )

    # ------------------------------------------------------------------
    # Narrative and report lifecycle
    # ------------------------------------------------------------------

    # Generated by ``generate_battle_report()`` from the outcome, losses,
    # territory transfer, and defender timeout state.
    battle_report = models.TextField(
        blank=True
    )

    # Dashboard queries resolved wars whose related Battle remains unseen.
    # Opening ``battle_report()`` changes this flag to True.
    report_seen = models.BooleanField(default=False)

    # Records the moment the Battle row was created.
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        """Define default reverse-chronological Battle ordering."""

        ordering = ["-created_at"]

    def __str__(self):
        """Return the participants and human-readable outcome."""
        return (
            f"{self.attacker.name} vs "
            f"{self.defender.name} "
            f"({self.get_outcome_display()})"
        )


class WarCooldown(models.Model):
    """Store a temporary directional restriction between two kingdoms.

    A cooldown row means that one specific attacker cannot target one specific
    defender until ``cooldown_ends_at``. Battle resolution creates cooldowns in
    both directions, preventing either participant from immediately attacking
    the other while still allowing unrelated opponents to remain eligible.
    """

    attacker = models.ForeignKey(
        Kingdom,

        # If the attacking kingdom is deleted, its directional cooldown records
        # no longer serve a purpose and are removed.
        on_delete=models.CASCADE,

        # Enables ``kingdom.war_cooldowns_started`` for restrictions where the
        # kingdom is the potential attacker.
        related_name="war_cooldowns_started",
    )

    defender = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,

        # Enables ``kingdom.war_cooldowns_received`` for restrictions protecting
        # the kingdom from specific attackers.
        related_name="war_cooldowns_received",
    )

    # The diplomacy queryset and declaration view compare this timestamp with
    # the current server time. Expired rows may remain stored but no longer
    # block a declaration.
    cooldown_ends_at = models.DateTimeField()

    class Meta:
        """Prevent duplicate cooldown rows for the same directional pairing."""

        # A single attacker-defender direction may have only one cooldown row.
        # ``resolve_war_simulation()`` uses update_or_create(), extending the
        # existing record instead of inserting a duplicate.
        unique_together = (
            "attacker",
            "defender",
        )

    def __str__(self):
        """Return a directional attacker-to-defender label."""
        return (
            f"{self.attacker.name} "
            f"→ {self.defender.name}"
        )