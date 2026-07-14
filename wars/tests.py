from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from kingdoms.models import Kingdom

from .forms import WarForm
from .models import Battle, War, WarCooldown
from .utils import momentum_hint_for_kingdom

# Create your tests here.

class WarsTestMixin:
    """Shared helpers for creating users, kingdoms, and wars."""

    def create_kingdom(self, username, kingdom_name, **overrides):
        user = User.objects.create_user(
            username=username,
            password="test-password-123",
        )
        defaults = {
            "owner": user,
            "name": kingdom_name,
            "ruler_name": f"Ruler of {kingdom_name}",
            "slug": kingdom_name.lower().replace(" ", "-"),
            "army_size": 100,
            "army_quality": 1.0,
            "war_available_until": timezone.now() + timedelta(hours=6),
        }
        defaults.update(overrides)
        kingdom = Kingdom.objects.create(**defaults)
        return user, kingdom

    def create_war(self, attacker, defender, **overrides):
        defaults = {
            "attacker": attacker,
            "defender": defender,
            "status": "pending_defender",
            "attacker_rallying_cry": (
                "Stand together with courage and defend the future of our realm."
            ),
        }
        defaults.update(overrides)
        return War.objects.create(**defaults)


class WarModelTests(WarsTestMixin, TestCase):
    def setUp(self):
        _, self.attacker = self.create_kingdom("attacker", "Northreach")
        _, self.defender = self.create_kingdom("defender", "Southwatch")

    def test_war_sets_default_response_deadline(self):
        before_creation = timezone.now()
        war = self.create_war(self.attacker, self.defender)

        self.assertIsNotNone(war.defender_response_deadline)
        self.assertGreater(
            war.defender_response_deadline,
            before_creation + timedelta(hours=2, minutes=59),
        )

    def test_war_has_expired_when_deadline_has_passed(self):
        war = self.create_war(
            self.attacker,
            self.defender,
            defender_response_deadline=timezone.now() - timedelta(minutes=1),
        )

        self.assertTrue(war.has_expired)

    def test_resolved_war_is_not_expired(self):
        war = self.create_war(
            self.attacker,
            self.defender,
            status="resolved",
            defender_response_deadline=timezone.now() - timedelta(minutes=1),
        )

        self.assertFalse(war.has_expired)

    def test_war_string_contains_both_kingdom_names(self):
        war = self.create_war(self.attacker, self.defender)

        self.assertEqual(str(war), "Northreach vs Southwatch")

    def test_battle_string_includes_displayed_outcome(self):
        war = self.create_war(
            self.attacker,
            self.defender,
            status="resolved",
        )
        battle = Battle.objects.create(
            war=war,
            attacker=self.attacker,
            defender=self.defender,
            outcome="attacker_victory",
        )

        self.assertEqual(
            str(battle),
            "Northreach vs Southwatch (Attacker Victory)",
        )

    def test_cooldown_string_shows_direction(self):
        cooldown = WarCooldown.objects.create(
            attacker=self.attacker,
            defender=self.defender,
            cooldown_ends_at=timezone.now() + timedelta(hours=24),
        )

        self.assertEqual(str(cooldown), "Northreach → Southwatch")


class WarFormTests(TestCase):
    def test_form_accepts_valid_rallying_cry_and_strips_spaces(self):
        rallying_cry = (
            "   Stand firm together and protect every family in our kingdom.   "
        )
        form = WarForm(data={"rallying_cry": rallying_cry})

        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.cleaned_data["rallying_cry"],
            rallying_cry.strip(),
        )

    def test_form_rejects_rallying_cry_shorter_than_thirty_characters(self):
        form = WarForm(data={"rallying_cry": "Too short"})

        self.assertFalse(form.is_valid())
        self.assertIn("rallying_cry", form.errors)


class MomentumHintTests(WarsTestMixin, TestCase):
    def setUp(self):
        _, self.kingdom = self.create_kingdom("scout", "Highvale")

    def test_hint_reports_high_confidence_for_strong_momentum(self):
        self.kingdom.battle_momentum = 8

        self.assertIn(
            "unusual confidence",
            momentum_hint_for_kingdom(self.kingdom),
        )

    def test_hint_reports_recent_setbacks_for_negative_momentum(self):
        self.kingdom.battle_momentum = -5

        self.assertIn(
            "recent setbacks",
            momentum_hint_for_kingdom(self.kingdom),
        )

    def test_hint_reports_badly_shaken_for_minimum_momentum(self):
        self.kingdom.battle_momentum = -8

        self.assertIn(
            "badly shaken",
            momentum_hint_for_kingdom(self.kingdom),
        )


class DiplomacyViewTests(WarsTestMixin, TestCase):
    def setUp(self):
        self.user, self.kingdom = self.create_kingdom(
            "player",
            "Oakenshield",
            army_size=100,
            army_quality=1.0,
        )

    def test_diplomacy_redirects_user_without_kingdom_to_create_kingdom(self):
        response = self.client.get(reverse("wars:diplomacy"))

        self.assertRedirects(
            response,
            reverse("create_kingdom"),
            fetch_redirect_response=False,
        )

    def test_diplomacy_lists_only_available_similar_strength_kingdoms(self):
        _, valid_enemy = self.create_kingdom(
            "valid_enemy",
            "Riverhold",
            army_size=110,
            army_quality=1.0,
        )
        self.create_kingdom(
            "too_strong",
            "Ironpeak",
            army_size=300,
            army_quality=1.0,
        )
        self.create_kingdom(
            "unavailable",
            "Mistwood",
            army_size=100,
            army_quality=1.0,
            war_available_until=timezone.now() - timedelta(minutes=1),
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("wars:diplomacy"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(valid_enemy, response.context["kingdoms"])
        self.assertNotIn(self.kingdom, response.context["kingdoms"])
        self.assertEqual(len(response.context["kingdoms"]), 1)

    def test_diplomacy_excludes_enemy_on_active_cooldown(self):
        _, enemy = self.create_kingdom(
            "enemy",
            "Stonegate",
            army_size=100,
            army_quality=1.0,
        )
        WarCooldown.objects.create(
            attacker=self.kingdom,
            defender=enemy,
            cooldown_ends_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("wars:diplomacy"))

        self.assertNotIn(enemy, response.context["kingdoms"])


class WarViewTests(WarsTestMixin, TestCase):
    def setUp(self):
        self.attacker_user, self.attacker = self.create_kingdom(
            "attacker_user",
            "Red Keep",
        )
        self.defender_user, self.defender = self.create_kingdom(
            "defender_user",
            "Blue Keep",
        )
        self.outsider_user, self.outsider = self.create_kingdom(
            "outsider_user",
            "Green Keep",
        )

    @patch("wars.views.evaluate_rallying_cry")
    def test_valid_declaration_creates_pending_war_and_updates_flags(
        self,
        mock_evaluate,
    ):
        mock_evaluate.return_value = {
            "leadership_score": 8,
            "inspiration_score": 7,
            "practicality_score": 6,
            "rally_modifier": 1.04,
            "feedback": "A convincing and practical command.",
        }
        self.client.force_login(self.attacker_user)
        response = self.client.post(
            reverse(
                "wars:declare_war",
                kwargs={"slug": self.defender.slug},
            ),
            {
                "rallying_cry": (
                    "Stand shoulder to shoulder and secure victory for our people."
                )
            },
        )

        self.assertRedirects(response, reverse("wars:war_pending"))
        war = War.objects.get(
            attacker=self.attacker,
            defender=self.defender,
        )
        self.assertEqual(war.status, "pending_defender")
        self.assertEqual(war.attacker_leadership_score, 8)
        self.attacker.refresh_from_db()
        self.defender.refresh_from_db()
        self.assertTrue(self.attacker.is_at_war)
        self.assertTrue(self.defender.is_at_war)

    def test_user_cannot_declare_war_on_own_kingdom(self):
        self.client.force_login(self.attacker_user)

        response = self.client.get(
            reverse(
                "wars:declare_war",
                kwargs={"slug": self.attacker.slug},
            )
        )

        self.assertRedirects(response, reverse("wars:diplomacy"))
        self.assertFalse(War.objects.exists())

    def test_war_list_shows_wars_started_and_received(self):
        started = self.create_war(self.attacker, self.defender)
        received = self.create_war(self.outsider, self.attacker)
        self.client.force_login(self.attacker_user)

        response = self.client.get(reverse("wars:war_list"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(started, response.context["wars_initiated"])
        self.assertIn(received, response.context["wars_received"])

    def test_defender_can_submit_rallying_cry(self):
        war = self.create_war(self.attacker, self.defender)
        self.client.force_login(self.defender_user)
        rallying_cry = (
            "Hold every gate, protect our people, and force the invaders back."
        )

        with patch("wars.views.evaluate_rallying_cry") as mock_evaluate:
            mock_evaluate.return_value = {
                "leadership_score": 9,
                "inspiration_score": 8,
                "practicality_score": 7,
                "rally_modifier": 1.05,
                "feedback": "A strong defensive command.",
            }
            response = self.client.post(
                reverse("wars:notify_defender"),
                {"rallying_cry": rallying_cry},
            )

        self.assertRedirects(response, reverse("wars:notify_defender"))
        war.refresh_from_db()
        self.assertEqual(war.defender_rallying_cry, rallying_cry)
        self.assertEqual(war.defender_rally_modifier, 1.05)

    def test_resolve_war_only_accepts_post_and_redirects_to_report(self):
        war = self.create_war(self.attacker, self.defender)
        self.client.force_login(self.defender_user)

        with patch("wars.views.resolve_war_simulation") as mock_resolve:
            response = self.client.post(reverse("wars:resolve_war"))

        mock_resolve.assert_called_once_with(war)

        self.assertRedirects(
            response,
            reverse("wars:battle_report", kwargs={"id": war.id}),
            fetch_redirect_response=False,
        )

    def test_battle_report_marks_report_as_seen_for_participant(self):
        war = self.create_war(
            self.attacker,
            self.defender,
            status="resolved",
        )
        battle = Battle.objects.create(
            war=war,
            attacker=self.attacker,
            defender=self.defender,
            outcome="draw",
            report_seen=False,
        )
        self.client.force_login(self.attacker_user)

        response = self.client.get(
            reverse("wars:battle_report", kwargs={"id": war.id})
        )

        self.assertEqual(response.status_code, 200)
        battle.refresh_from_db()
        self.assertTrue(battle.report_seen)
        self.assertTrue(response.context["was_unseen"])

    def test_outsider_cannot_view_battle_report(self):
        war = self.create_war(
            self.attacker,
            self.defender,
            status="resolved",
        )
        Battle.objects.create(
            war=war,
            attacker=self.attacker,
            defender=self.defender,
            outcome="draw",
        )
        self.client.force_login(self.outsider_user)

        response = self.client.get(
            reverse("wars:battle_report", kwargs={"id": war.id})
        )

        self.assertEqual(response.status_code, 404)