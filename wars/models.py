from datetime import timedelta
from django.db import models
from django.utils import timezone
from kingdoms.models import Kingdom

class War(models.Model):
    STATUS_CHOICES = [
        ("pending_defender", "Pending Defender Response"),
        ("resolved", "Resolved"),
    ]

    attacker = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="wars_started",
    )

    defender = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="wars_received",
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="pending_defender",
    )

    declared_at = models.DateTimeField(
        auto_now_add=True
    )

    defender_response_deadline = models.DateTimeField()

    resolved_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    winner = models.ForeignKey(
        Kingdom,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wars_won_records",
    )

    # ----------------------------
    # Attacker Rallying Cry
    # ----------------------------

    attacker_rallying_cry = models.TextField()

    attacker_leadership_score = models.FloatField(default=0)
    attacker_inspiration_score = models.FloatField(default=0)
    attacker_practicality_score = models.FloatField(default=0)

    attacker_rally_modifier = models.FloatField(default=1.0)

    attacker_ai_feedback = models.TextField(
        blank=True
    )

    # ----------------------------
    # Defender Rallying Cry
    # ----------------------------

    defender_rallying_cry = models.TextField(
        blank=True
    )

    defender_leadership_score = models.FloatField(default=0)
    defender_inspiration_score = models.FloatField(default=0)
    defender_practicality_score = models.FloatField(default=0)

    defender_rally_modifier = models.FloatField(default=1.0)

    defender_ai_feedback = models.TextField(
        blank=True
    )

    defender_responded_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    defender_auto_resolved = models.BooleanField(
        default=False
    )

    class Meta:
        ordering = ["-declared_at"]

    def save(self, *args, **kwargs):
        if not self.defender_response_deadline:
            self.defender_response_deadline = (
                timezone.now() + timedelta(hours=3)
            )

        super().save(*args, **kwargs)

    @property
    def has_expired(self):
        return (
            self.status == "pending_defender"
            and timezone.now() >= self.defender_response_deadline
        )

    def __str__(self):
        return f"{self.attacker.name} vs {self.defender.name}"


class Battle(models.Model):

    OUTCOME_CHOICES = [
        ("attacker_victory", "Attacker Victory"),
        ("defender_victory", "Defender Victory"),
        ("draw", "Draw"),
    ]

    war = models.OneToOneField(
        War,
        on_delete=models.CASCADE,
        related_name="battle",
    )

    attacker = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="attacking_battles",
    )

    defender = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="defending_battles",
    )

    # ----------------------------
    # Hidden Modifiers
    # ----------------------------

    attacker_momentum_modifier = models.FloatField(
        default=1.0
    )

    defender_momentum_modifier = models.FloatField(
        default=1.0
    )

    attacker_prestige_modifier = models.FloatField(
        default=1.0
    )

    defender_prestige_modifier = models.FloatField(
        default=1.0
    )

    attacker_random_factor = models.FloatField(
        default=1.0
    )

    defender_random_factor = models.FloatField(
        default=1.0
    )

    # ----------------------------
    # Final Strengths
    # ----------------------------

    attacker_strength = models.FloatField(default=0)

    defender_strength = models.FloatField(default=0)

    # ----------------------------
    # Results
    # ----------------------------

    outcome = models.CharField(
        max_length=30,
        choices=OUTCOME_CHOICES,
    )

    attacker_losses = models.PositiveIntegerField(
        default=0
    )

    defender_losses = models.PositiveIntegerField(
        default=0
    )

    # ----------------------------
    # Narrative
    # ----------------------------

    battle_report = models.TextField(
        blank=True
    )

    battle_log = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.attacker.name} vs "
            f"{self.defender.name} "
            f"({self.get_outcome_display()})"
        )


class WarCooldown(models.Model):

    attacker = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="war_cooldowns_started",
    )

    defender = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="war_cooldowns_received",
    )

    cooldown_ends_at = models.DateTimeField()

    class Meta:
        unique_together = (
            "attacker",
            "defender",
        )

    def __str__(self):
        return (
            f"{self.attacker.name} "
            f"→ {self.defender.name}"
        )