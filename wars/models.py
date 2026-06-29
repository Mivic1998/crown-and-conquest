from django.db import models

from kingdoms.models import Kingdom


class War(models.Model):

    STATUS_CHOICES = [
        ("active", "Active"),
        ("peace_offered", "Peace Offered"),
        ("ended", "Ended"),
    ]

    attacker = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="wars_started"
    )

    defender = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="wars_defended"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active"
    )

    declared_at = models.DateTimeField(
        auto_now_add=True
    )

    ended_at = models.DateTimeField(
        blank=True,
        null=True
    )

    winner = models.ForeignKey(
        Kingdom,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wars_won"
    )

    class Meta:
        ordering = ["-declared_at"]

    def __str__(self):
        return (
            f"{self.attacker.name} vs "
            f"{self.defender.name}"
        )
    
class WarParticipant(models.Model):

    SIDE_CHOICES = [
        ("attacker", "Attacker"),
        ("defender", "Defender"),
    ]

    war = models.ForeignKey(
        War,
        on_delete=models.CASCADE,
        related_name="participants"
    )

    kingdom = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="war_participations"
    )

    side = models.CharField(
        max_length=20,
        choices=SIDE_CHOICES
    )

    troops_committed = models.IntegerField(
        default=0
    )

    starting_army_quality = models.FloatField()

    joined_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        unique_together = ("war", "kingdom")

    def __str__(self):
        return (
            f"{self.kingdom.name} "
            f"({self.side})"
        )
    
class Battle(models.Model):

    OUTCOME_CHOICES = [
        ("attacker_victory", "Attacker Victory"),
        ("defender_victory", "Defender Victory"),
        ("draw", "Draw"),
    ]

    war = models.ForeignKey(
        War,
        on_delete=models.CASCADE,
        related_name="battles"
    )

    attacker = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="attacking_battles"
    )

    defender = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="defending_battles"
    )

    attacker_losses = models.IntegerField(
        default=0
    )

    defender_losses = models.IntegerField(
        default=0
    )

    outcome = models.CharField(
        max_length=30,
        choices=OUTCOME_CHOICES
    )

    battle_log = models.JSONField(
        default=dict,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Battle in War #{self.war.id}"
        )
    
class PeaceOffer(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("withdrawn", "Withdrawn"),
    ]

    war = models.ForeignKey(
        War,
        on_delete=models.CASCADE,
        related_name="peace_offers"
    )

    offered_by = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="peace_offers_sent"
    )

    offered_to = models.ForeignKey(
        Kingdom,
        on_delete=models.CASCADE,
        related_name="peace_offers_received"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    terms = models.JSONField(
        default=dict,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    responded_at = models.DateTimeField(
        blank=True,
        null=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Peace Offer: "
            f"{self.offered_by.name} → "
            f"{self.offered_to.name}"
        )