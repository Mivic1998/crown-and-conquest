from django.db import models
from django.utils import timezone
from datetime import timedelta

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
        related_name="wars_defended",
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="pending_defender",
    )

    declared_at = models.DateTimeField(auto_now_add=True)

    defender_response_deadline = models.DateTimeField(
        blank=True,
        null=True,
    )

    resolved_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    winner = models.ForeignKey(
        Kingdom,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wars_won",
    )

    # Attacker rallying cry
    attacker_rallying_cry = models.TextField()

    attacker_leadership_score = models.FloatField(default=0)
    attacker_inspiration_score = models.FloatField(default=0)
    attacker_practicality_score = models.FloatField(default=0)
    attacker_rallying_cry_modifier = models.FloatField(default=1.0)
    attacker_rallying_cry_feedback = models.TextField(blank=True)

    # Defender rallying cry
    defender_rallying_cry = models.TextField(blank=True)

    defender_leadership_score = models.FloatField(default=0)
    defender_inspiration_score = models.FloatField(default=0)
    defender_practicality_score = models.FloatField(default=0)
    defender_rallying_cry_modifier = models.FloatField(default=1.0)
    defender_rallying_cry_feedback = models.TextField(blank=True)

    defender_responded_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    defender_auto_resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["-declared_at"]

    def save(self, *args, **kwargs):
        if not self.defender_response_deadline:
            self.defender_response_deadline = timezone.now() + timedelta(hours=3)
        super().save(*args, **kwargs)

    @property
    def is_pending(self):
        return self.status == "pending_defender"

    @property
    def response_expired(self):
        return (
            self.status == "pending_defender"
            and self.defender_response_deadline
            and timezone.now() >= self.defender_response_deadline
        )

    def __str__(self):
        return f"{self.attacker.name} vs {self.defender.name}"