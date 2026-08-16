"""Tests for warfare models, forms, utilities, diplomacy, and war workflows.

This module verifies several layers of the ``wars`` application:

- War, Battle, and WarCooldown model behaviour;
- rallying-cry form validation;
- momentum-hint utility output;
- diplomacy filtering and cooldown exclusions;
- war declaration, defender response, resolution, and report permissions;
- integration boundaries around Gemini evaluation and battle simulation.

The suite combines direct model, form, and utility tests with Django view
integration tests. External or complex dependencies are patched where the test
should verify the surrounding workflow rather than execute Gemini or the full
battle simulation.
"""

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


class WarsTestMixin:
    """Provide reusable factories for warfare users, kingdoms, and wars."""

    def create_kingdom(self, username, kingdom_name, **overrides):
        """Create a user and an owned kingdom suitable for warfare tests.

        Args:
            username: Username for the new Django user.
            kingdom_name: Public name assigned to the related Kingdom.
            **overrides: Optional Kingdom values replacing the defaults.

        Returns:
            A tuple containing the created User and Kingdom.

        The default kingdom is deliberately available for war and has predictable
        military values. Individual tests may override army strength,
        availability, or other fields to exercise filtering and permissions.
        """
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

            # Diplomacy only lists kingdoms whose availability window remains
            # active, so the shared default places the expiry six hours ahead.
            "war_available_until": timezone.now() + timedelta(hours=6),
        }

        # Allow each test to vary only the fields relevant to its scenario.
        defaults.update(overrides)

        kingdom = Kingdom.objects.create(**defaults)

        return user, kingdom

    def create_war(self, attacker, defender, **overrides):
        """Create a pending War between two kingdoms.

        Args:
            attacker: Kingdom initiating the conflict.
            defender: Kingdom receiving the declaration.
            **overrides: Optional War values replacing the defaults.

        Returns:
            The newly created War.

        A sufficiently long attacker rallying cry is supplied so tests not
        concerned with form validation begin with a realistic pending record.
        """
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
    """Test warfare model defaults, properties, and string representations."""

    def setUp(self):
        """Create attacker and defender kingdoms before each model test."""
        _, self.attacker = self.create_kingdom(
            "attacker",
            "Northreach",
        )
        _, self.defender = self.create_kingdom(
            "defender",
            "Southwatch",
        )

    def test_war_sets_default_response_deadline(self):
        """Confirm that a new War receives an approximately three-hour deadline."""
        # Capture server time immediately before creation so the generated
        # deadline can be compared with the expected three-hour window.
        before_creation = timezone.now()

        war = self.create_war(
            self.attacker,
            self.defender,
        )

        self.assertIsNotNone(war.defender_response_deadline)

        # The threshold allows a small amount of execution time while proving
        # that the model created a deadline very close to three hours ahead.
        self.assertGreater(
            war.defender_response_deadline,
            before_creation + timedelta(hours=2, minutes=59),
        )

    def test_war_has_expired_when_deadline_has_passed(self):
        """Confirm that a pending War is expired after its response deadline."""
        war = self.create_war(
            self.attacker,
            self.defender,

            # Supplying a past deadline directly exercises the property without
            # waiting for real time to pass.
            defender_response_deadline=(
                timezone.now() - timedelta(minutes=1)
            ),
        )

        self.assertTrue(war.has_expired)

    def test_resolved_war_is_not_expired(self):
        """Confirm that resolved Wars are excluded from pending-expiry logic."""
        war = self.create_war(
            self.attacker,
            self.defender,
            status="resolved",
            defender_response_deadline=(
                timezone.now() - timedelta(minutes=1)
            ),
        )

        # The property requires both a past deadline and pending-defender status.
        self.assertFalse(war.has_expired)

    def test_war_string_contains_both_kingdom_names(self):
        """Verify the readable War string representation."""
        war = self.create_war(
            self.attacker,
            self.defender,
        )

        self.assertEqual(
            str(war),
            "Northreach vs Southwatch",
        )

    def test_battle_string_includes_displayed_outcome(self):
        """Verify that Battle.__str__ includes the human-readable outcome."""
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

        # get_outcome_display() converts the stored choice value into
        # "Attacker Victory" inside the model's string method.
        self.assertEqual(
            str(battle),
            "Northreach vs Southwatch (Attacker Victory)",
        )

    def test_cooldown_string_shows_direction(self):
        """Confirm that a cooldown string identifies its attack direction."""
        cooldown = WarCooldown.objects.create(
            attacker=self.attacker,
            defender=self.defender,
            cooldown_ends_at=(
                timezone.now() + timedelta(hours=24)
            ),
        )

        # Direction matters because cooldowns are stored per attacker/defender
        # pair rather than as one undirected relationship.
        self.assertEqual(
            str(cooldown),
            "Northreach → Southwatch",
        )


class WarFormTests(TestCase):
    """Test player-facing rallying-cry validation and normalisation."""

    def test_form_accepts_valid_rallying_cry_and_strips_spaces(self):
        """Confirm that valid text passes and surrounding whitespace is removed."""
        rallying_cry = (
            "   Stand firm together and protect every family in our kingdom.   "
        )

        form = WarForm(
            data={"rallying_cry": rallying_cry}
        )

        self.assertTrue(form.is_valid())

        # clean_rallying_cry() replaces the submitted value in cleaned_data with
        # a normalised version before views send it to Gemini or save it.
        self.assertEqual(
            form.cleaned_data["rallying_cry"],
            rallying_cry.strip(),
        )

    def test_form_rejects_rallying_cry_shorter_than_thirty_characters(self):
        """Confirm that a trivial rallying cry fails minimum-length validation."""
        form = WarForm(
            data={"rallying_cry": "Too short"}
        )

        self.assertFalse(form.is_valid())

        # The failure is attached to the rallying_cry field so Django can render
        # the message beside the textarea.
        self.assertIn(
            "rallying_cry",
            form.errors,
        )


class MomentumHintTests(WarsTestMixin, TestCase):
    """Test qualitative scouting text derived from battle momentum."""

    def setUp(self):
        """Create one kingdom whose momentum can be varied in each test."""
        _, self.kingdom = self.create_kingdom(
            "scout",
            "Highvale",
        )

    def test_hint_reports_high_confidence_for_strong_momentum(self):
        """Confirm that strongly positive momentum yields a confident hint."""
        self.kingdom.battle_momentum = 8

        self.assertIn(
            "unusual confidence",
            momentum_hint_for_kingdom(self.kingdom),
        )

    def test_hint_reports_recent_setbacks_for_negative_momentum(self):
        """Confirm that moderately negative momentum reports recent setbacks."""
        self.kingdom.battle_momentum = -5

        self.assertIn(
            "recent setbacks",
            momentum_hint_for_kingdom(self.kingdom),
        )

    def test_hint_reports_badly_shaken_for_minimum_momentum(self):
        """Confirm that severe negative momentum produces the strongest warning."""
        self.kingdom.battle_momentum = -8

        self.assertIn(
            "badly shaken",
            momentum_hint_for_kingdom(self.kingdom),
        )


class DiplomacyViewTests(WarsTestMixin, TestCase):
    """Test diplomacy access and filtering of eligible opponents."""

    def setUp(self):
        """Create the player's kingdom without authenticating the client."""
        self.user, self.kingdom = self.create_kingdom(
            "player",
            "Oakenshield",
            army_size=100,
            army_quality=1.0,
        )

    def test_diplomacy_redirects_user_without_kingdom_to_create_kingdom(self):
        """Confirm that an unauthenticated/no-kingdom request is redirected."""
        response = self.client.get(
            reverse("wars:diplomacy")
        )

        # The view cannot present opponent choices without an owned Kingdom, so
        # it redirects toward the kingdom-creation workflow.
        self.assertRedirects(
            response,
            reverse("create_kingdom"),
            fetch_redirect_response=False,
        )

    def test_diplomacy_lists_only_available_similar_strength_kingdoms(self):
        """Verify that diplomacy includes only eligible, comparable opponents."""
        _, valid_enemy = self.create_kingdom(
            "valid_enemy",
            "Riverhold",
            army_size=110,
            army_quality=1.0,
        )

        # This kingdom is available but deliberately far stronger than the
        # player's force and should be excluded by strength filtering.
        self.create_kingdom(
            "too_strong",
            "Ironpeak",
            army_size=300,
            army_quality=1.0,
        )

        # This kingdom has comparable strength but an expired availability
        # window, so it should also be excluded.
        self.create_kingdom(
            "unavailable",
            "Mistwood",
            army_size=100,
            army_quality=1.0,
            war_available_until=(
                timezone.now() - timedelta(minutes=1)
            ),
        )

        self.client.force_login(self.user)

        response = self.client.get(
            reverse("wars:diplomacy")
        )

        self.assertEqual(response.status_code, 200)

        # Riverhold satisfies both availability and strength requirements.
        self.assertIn(
            valid_enemy,
            response.context["kingdoms"],
        )

        # The current player's own kingdom must never appear as a target.
        self.assertNotIn(
            self.kingdom,
            response.context["kingdoms"],
        )

        # Proves that the two deliberately invalid opponents were excluded.
        self.assertEqual(
            len(response.context["kingdoms"]),
            1,
        )

    def test_diplomacy_excludes_enemy_on_active_cooldown(self):
        """Confirm that an active directional cooldown removes an opponent."""
        _, enemy = self.create_kingdom(
            "enemy",
            "Stonegate",
            army_size=100,
            army_quality=1.0,
        )

        WarCooldown.objects.create(
            attacker=self.kingdom,
            defender=enemy,
            cooldown_ends_at=(
                timezone.now() + timedelta(hours=1)
            ),
        )

        self.client.force_login(self.user)

        response = self.client.get(
            reverse("wars:diplomacy")
        )

        # The opponent would otherwise satisfy availability and strength rules.
        self.assertNotIn(
            enemy,
            response.context["kingdoms"],
        )


class WarViewTests(WarsTestMixin, TestCase):
    """Test declaration, response, resolution, listing, and report permissions."""

    def setUp(self):
        """Create attacker, defender, and unrelated outsider kingdoms."""
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
        """Verify the successful declaration workflow without calling Gemini."""
        # Patch the name imported by wars.views because that is the reference the
        # production view invokes. Patching core.ai directly would not replace an
        # already imported local reference inside wars.views.
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
                    "Stand shoulder to shoulder and secure victory "
                    "for our people."
                )
            },
        )

        self.assertRedirects(
            response,
            reverse("wars:war_pending"),
        )

        # Querying by both participants proves that the correct conflict was
        # created rather than relying only on a redirect.
        war = War.objects.get(
            attacker=self.attacker,
            defender=self.defender,
        )

        self.assertEqual(
            war.status,
            "pending_defender",
        )

        # Confirms that the mocked AI result is mapped into the War record.
        self.assertEqual(
            war.attacker_leadership_score,
            8,
        )

        # Reload both kingdoms because the view updates their persisted war flags.
        self.attacker.refresh_from_db()
        self.defender.refresh_from_db()

        self.assertTrue(self.attacker.is_at_war)
        self.assertTrue(self.defender.is_at_war)

    def test_user_cannot_declare_war_on_own_kingdom(self):
        """Confirm that a kingdom cannot target itself."""
        self.client.force_login(self.attacker_user)

        response = self.client.get(
            reverse(
                "wars:declare_war",
                kwargs={"slug": self.attacker.slug},
            )
        )

        self.assertRedirects(
            response,
            reverse("wars:diplomacy"),
        )

        # The database assertion proves that the invalid request produced no
        # hidden conflict record.
        self.assertFalse(War.objects.exists())

    def test_war_list_shows_wars_started_and_received(self):
        """Verify that war history is separated by participant role."""
        started = self.create_war(
            self.attacker,
            self.defender,
        )
        received = self.create_war(
            self.outsider,
            self.attacker,
        )

        self.client.force_login(self.attacker_user)

        response = self.client.get(
            reverse("wars:war_list")
        )

        self.assertEqual(response.status_code, 200)

        # The authenticated kingdom appears as attacker in the initiated list.
        self.assertIn(
            started,
            response.context["wars_initiated"],
        )

        # The authenticated kingdom appears as defender in the received list.
        self.assertIn(
            received,
            response.context["wars_received"],
        )

    def test_defender_can_submit_rallying_cry(self):
        """Verify defender form handling, AI mapping, persistence, and redirect."""
        war = self.create_war(
            self.attacker,
            self.defender,
        )

        self.client.force_login(self.defender_user)

        rallying_cry = (
            "Hold every gate, protect our people, and force the invaders back."
        )

        # The context-manager patch limits the mock to this request and prevents
        # a real Gemini network call.
        with patch(
            "wars.views.evaluate_rallying_cry"
        ) as mock_evaluate:
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

        self.assertRedirects(
            response,
            reverse("wars:notify_defender"),
        )

        # Reload to verify the values written by the view rather than the
        # pre-request in-memory War object.
        war.refresh_from_db()

        self.assertEqual(
            war.defender_rallying_cry,
            rallying_cry,
        )
        self.assertEqual(
            war.defender_rally_modifier,
            1.05,
        )

    def test_resolve_war_only_accepts_post_and_redirects_to_report(self):
        """Verify POST resolution delegates to the simulation and redirects."""
        war = self.create_war(
            self.attacker,
            self.defender,
        )

        self.client.force_login(self.defender_user)

        # The full simulation has many side effects and independent tests should
        # cover its formulas. This view test only verifies delegation and routing.
        with patch(
            "wars.views.resolve_war_simulation"
        ) as mock_resolve:
            response = self.client.post(
                reverse("wars:resolve_war")
            )

        # The exact War instance selected by the view must be passed to the
        # simulation service once.
        mock_resolve.assert_called_once_with(war)

        self.assertRedirects(
            response,
            reverse(
                "wars:battle_report",
                kwargs={"id": war.id},
            ),
            fetch_redirect_response=False,
        )

    def test_battle_report_marks_report_as_seen_for_participant(self):
        """Confirm that a participant viewing a new report marks it as seen."""
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
            reverse(
                "wars:battle_report",
                kwargs={"id": war.id},
            )
        )

        self.assertEqual(response.status_code, 200)

        # The view mutates report_seen, so refresh_from_db() verifies persistence.
        battle.refresh_from_db()

        self.assertTrue(battle.report_seen)

        # The context preserves the pre-update state so the template can display
        # new-report messaging even after report_seen has been saved as True.
        self.assertTrue(response.context["was_unseen"])

    def test_outsider_cannot_view_battle_report(self):
        """Confirm that a non-participant receives a 404 for a battle report."""
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
            reverse(
                "wars:battle_report",
                kwargs={"id": war.id},
            )
        )

        # Returning 404 avoids exposing whether a private conflict exists while
        # enforcing that only attacker and defender may inspect the report.
        self.assertEqual(response.status_code, 404)