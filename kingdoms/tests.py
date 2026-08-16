"""Tests for kingdom models, turn limits, forms, and core kingdom views.

This module verifies several layers of the ``kingdoms`` application:

- Kingdom model properties and warfare-availability helpers;
- TurnLimit allowance, cooldown, and daily-reset behaviour;
- policy-form validation;
- premium settings-field restrictions;
- kingdom creation, dashboard access, turn-history ownership, and deletion.

The tests combine direct model and form unit tests with Django view integration
tests. Django's ``TestCase`` provides an isolated test database and a fresh test
client for every test, so records created or deleted in one test do not affect
the others.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import KingdomSettingsForm, PolicyForm
from .models import Kingdom, TurnHistory, TurnLimit
from .utils import next_midnight


class KingdomModelTests(TestCase):
    """Test Kingdom display behaviour and calculated helper properties."""

    def setUp(self):
        """Create one user and owned kingdom before each model test.

        The Kingdom is created with only the required identity fields, allowing
        the model's defaults to establish its initial economic, military, policy,
        warfare, and premium state.
        """
        self.user = User.objects.create_user(
            username="arthur",
            password="testpass123",
        )

        # Kingdom.owner is one-to-one, so this user can own only this Kingdom.
        self.kingdom = Kingdom.objects.create(
            owner=self.user,
            name="Camelot",
            ruler_name="Arthur",
            slug="camelot",
        )

    def test_string_method_returns_kingdom_name(self):
        """Confirm that Kingdom.__str__ returns its public name."""
        # A readable string representation is used by Django admin, the shell,
        # debugging output, and relationship displays.
        self.assertEqual(str(self.kingdom), "Camelot")

    def test_leaderboard_score_uses_territory_and_population(self):
        """Verify the derived leaderboard-score formula."""
        # The property is calculated from the current in-memory values and does
        # not require a save because it is not a database field.
        self.kingdom.territory_count = 60
        self.kingdom.population = 2000

        # Expected calculation:
        # 60 territories × 1,000 = 60,000
        # 2,000 population × 0.1 = 200
        # total = 60,200
        self.assertEqual(self.kingdom.leaderboard_score, 60200)

    def test_wolf_crest_unlocks_at_required_score(self):
        """Confirm that the wolf crest unlocks at the required score."""
        # A territory count of 150 creates a score of exactly 150,000 when
        # population is zero, matching WOLF_CREST_SCORE_REQUIREMENT.
        self.kingdom.territory_count = 150
        self.kingdom.population = 0

        self.assertTrue(self.kingdom.has_wolf_crest_unlocked)

    def test_refresh_war_availability_sets_future_expiry(self):
        """Verify that activity refreshes the kingdom's war-availability window."""
        # Capture the current time before the method runs so the saved expiry can
        # be proved to lie in the future.
        before = timezone.now()

        # The model method updates last_active_at and extends
        # war_available_until by the supplied number of hours.
        self.kingdom.refresh_war_availability(hours=6)

        # Reload the instance because the assertions should verify persisted
        # database values rather than only the in-memory assignments.
        self.kingdom.refresh_from_db()

        self.assertIsNotNone(self.kingdom.last_active_at)
        self.assertGreater(self.kingdom.war_available_until, before)

        # is_available_for_war() compares the stored timestamp with server time.
        self.assertTrue(self.kingdom.is_available_for_war())


class TurnLimitModelTests(TestCase):
    """Test daily allowances, premium limits, cooldowns, and resets."""

    def setUp(self):
        """Create a standard kingdom with an explicit TurnLimit record."""
        user = User.objects.create_user(
            username="guinevere",
            password="testpass123",
        )

        self.kingdom = Kingdom.objects.create(
            owner=user,
            name="Avalon",
            ruler_name="Guinevere",
            slug="avalon",
        )

        # TurnLimit is one-to-one with Kingdom. The reset timestamp is generated
        # through the same utility used by production kingdom creation.
        self.turn_limit = TurnLimit.objects.create(
            kingdom=self.kingdom,
            daily_turn_limit=3,
            turns_remaining_today=3,
            cooldown_minutes=120,
            daily_reset_at=next_midnight(),
        )

    def test_free_kingdom_has_three_daily_turns(self):
        """Confirm the standard daily allowance returned by the model helper."""
        self.assertEqual(self.turn_limit.premium_daily_limit(), 3)

    def test_premium_kingdom_has_six_daily_turns(self):
        """Confirm that premium status doubles the daily allowance to six."""
        # premium_daily_limit() reads Kingdom.is_premium dynamically, so only
        # the entitlement field needs to be changed for this test.
        self.kingdom.is_premium = True
        self.kingdom.save(update_fields=["is_premium"])

        self.assertEqual(self.turn_limit.premium_daily_limit(), 6)

    def test_use_turn_reduces_turns_and_starts_cooldown(self):
        """Verify the complete state transition performed by use_turn()."""
        # use_turn() decrements the allowance, records the action timestamp, and
        # calculates cooldown_ends_at from cooldown_minutes.
        self.turn_limit.use_turn()
        self.turn_limit.refresh_from_db()

        self.assertEqual(self.turn_limit.turns_remaining_today, 2)
        self.assertIsNotNone(self.turn_limit.last_turn_taken_at)
        self.assertTrue(self.turn_limit.cooldown_active())

        # A kingdom with remaining daily turns still cannot proceed while the
        # between-turn cooldown remains active.
        self.assertFalse(self.turn_limit.can_take_turn())

    def test_refresh_daily_turns_resets_expired_limit(self):
        """Confirm that an expired daily reset replenishes the allowance."""
        # Establish the expired state deliberately: no turns remain and the reset
        # timestamp is one minute in the past.
        self.turn_limit.turns_remaining_today = 0
        self.turn_limit.daily_reset_at = (
            timezone.now() - timedelta(minutes=1)
        )
        self.turn_limit.save()

        # refresh_daily_turns() recalculates the premium-aware limit, replenishes
        # turns, and schedules the next reset.
        self.turn_limit.refresh_daily_turns()
        self.turn_limit.refresh_from_db()

        self.assertEqual(self.turn_limit.turns_remaining_today, 3)
        self.assertGreater(
            self.turn_limit.daily_reset_at,
            timezone.now(),
        )


class PolicyFormTests(TestCase):
    """Test player-facing taxation and investment validation."""

    def valid_data(self):
        """Return a complete valid policy allocation.

        The four investments total exactly 100%, while taxation remains within
        the accepted 0–50 range.
        """
        return {
            "tax_rate": 20,
            "agriculture_investment": 25,
            "infrastructure_investment": 25,
            "military_investment": 25,
            "welfare_investment": 25,
        }

    def test_valid_policy_form(self):
        """Confirm that a balanced policy allocation passes validation."""
        self.assertTrue(
            PolicyForm(data=self.valid_data()).is_valid()
        )

    def test_tax_rate_must_be_between_zero_and_fifty(self):
        """Confirm that taxation above the permitted maximum is rejected."""
        data = self.valid_data()
        data["tax_rate"] = 60

        form = PolicyForm(data=data)

        self.assertFalse(form.is_valid())

        # clean_tax_rate() attaches the validation error directly to tax_rate.
        self.assertIn("tax_rate", form.errors)

    def test_investments_must_total_one_hundred(self):
        """Confirm that an incomplete investment allocation is rejected."""
        data = self.valid_data()

        # Reducing welfare causes the combined allocation to total 85 rather
        # than the required 100.
        data["welfare_investment"] = 10

        form = PolicyForm(data=data)

        self.assertFalse(form.is_valid())

        # The rule depends on all four fields, so PolicyForm.clean() raises a
        # non-field error rather than attaching it to one investment.
        self.assertIn(
            (
                "Agriculture, infrastructure, military, and welfare "
                "investments must total 100."
            ),
            form.non_field_errors(),
        )


class KingdomSettingsFormTests(TestCase):
    """Test premium appearance restrictions and crest unlock filtering."""

    def setUp(self):
        """Create a standard non-premium kingdom for each settings test."""
        user = User.objects.create_user(username="lancelot")

        self.kingdom = Kingdom.objects.create(
            owner=user,
            name="Joyous Gard",
            ruler_name="Lancelot",
            slug="joyous-gard",
        )

    def test_free_user_cannot_edit_premium_appearance_fields(self):
        """Verify that premium-only appearance fields are removed entirely."""
        form = KingdomSettingsForm(
            instance=self.kingdom,
            kingdom=self.kingdom,
        )

        # Removing these fields from self.fields is stronger than hiding them in
        # HTML: manipulated POST values will not enter cleaned_data or be saved.
        self.assertNotIn("banner_colour", form.fields)
        self.assertNotIn("crest", form.fields)

    def test_locked_wolf_crest_is_not_offered_to_premium_user(self):
        """Confirm that premium status alone does not unlock the wolf crest."""
        self.kingdom.is_premium = True
        self.kingdom.save(update_fields=["is_premium"])

        form = KingdomSettingsForm(
            instance=self.kingdom,
            kingdom=self.kingdom,
        )

        # Choice tuples contain the stored value and human-readable label. Only
        # the stored values are needed to verify that "wolf" was filtered out.
        crest_values = [
            value
            for value, _ in form.fields["crest"].choices
        ]

        self.assertNotIn("wolf", crest_values)


class KingdomViewTests(TestCase):
    """Test kingdom creation, dashboard access, history isolation, and deletion."""

    def setUp(self):
        """Create and authenticate a user before each view test."""
        self.user = User.objects.create_user(
            username="merlin",
            password="testpass123",
        )

        # login() tests normal credential-based session creation. Its return
        # value is not asserted because later view responses prove that the
        # authenticated session is active.
        self.client.login(
            username="merlin",
            password="testpass123",
        )

    def create_kingdom(self, **overrides):
        """Create the logged-in user's Kingdom and related TurnLimit.

        Args:
            **overrides: Optional Kingdom values replacing the defaults.

        Returns:
            The newly created Kingdom.

        Production kingdom creation creates both objects. Reproducing that
        relationship here keeps dashboard and turn-related view tests in a valid
        application state.
        """
        data = {
            "owner": self.user,
            "name": "Albion",
            "ruler_name": "Merlin",
            "slug": "albion",
        }

        data.update(overrides)

        kingdom = Kingdom.objects.create(**data)

        # Match the production entitlement rule: premium kingdoms receive six
        # turns, while ordinary kingdoms receive three.
        limit = 6 if kingdom.is_premium else 3

        TurnLimit.objects.create(
            kingdom=kingdom,
            daily_turn_limit=limit,
            turns_remaining_today=limit,
            daily_reset_at=next_midnight(),
        )

        return kingdom

    def test_create_kingdom_creates_kingdom_and_turn_limit(self):
        """Verify the complete successful kingdom-creation workflow."""
        response = self.client.post(
            reverse("create_kingdom"),
            {"name": "Albion"},
        )

        self.assertRedirects(
            response,
            reverse("dashboard"),
        )

        # Retrieve the persisted Kingdom through its one-to-one owner relation.
        kingdom = Kingdom.objects.get(owner=self.user)

        # The view derives ruler_name from the authenticated username rather than
        # trusting an additional browser-supplied field.
        self.assertEqual(kingdom.ruler_name, "merlin")

        # The view generates the URL-safe slug from the validated kingdom name.
        self.assertEqual(kingdom.slug, "albion")

        # A usable kingdom must receive its one-to-one TurnLimit during creation.
        self.assertTrue(
            TurnLimit.objects.filter(kingdom=kingdom).exists()
        )

    def test_existing_owner_is_redirected_from_create_page(self):
        """Confirm that a user cannot create a second kingdom."""
        self.create_kingdom()

        response = self.client.get(
            reverse("create_kingdom")
        )

        # The User-to-Kingdom one-to-one relationship is reinforced at the view
        # level by redirecting existing owners to their dashboard.
        self.assertRedirects(
            response,
            reverse("dashboard"),
        )

    def test_dashboard_redirects_user_without_kingdom(self):
        """Confirm that authenticated users must create a kingdom first."""
        response = self.client.get(reverse("dashboard"))

        self.assertRedirects(
            response,
            reverse("create_kingdom"),
        )

    def test_dashboard_displays_owned_kingdom(self):
        """Verify that the dashboard uses the authenticated user's kingdom."""
        kingdom = self.create_kingdom()

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)

        # The context object proves that the view selected the correct owned
        # Kingdom rather than a different or arbitrary record.
        self.assertEqual(
            response.context["kingdom"],
            kingdom,
        )

        # Visible-content verification complements the context assertion by
        # proving the template renders the kingdom's name.
        self.assertContains(response, "Albion")

    def test_turn_history_only_contains_current_users_turns(self):
        """Verify that turn history is isolated by kingdom ownership."""
        kingdom = self.create_kingdom()

        # Create one historical snapshot belonging to the authenticated user's
        # Kingdom.
        TurnHistory.objects.create(
            kingdom=kingdom,
            turn_number=1,
            population=1000,
            treasury=500,
            food=1000,
            happiness=50,
            stability=50,
            army_size=100,
            army_quality=1,
            a_eff=1,
            infra=1,
            tax_rate=20,
            agriculture_investment=25,
            infrastructure_investment=25,
            military_investment=25,
            welfare_investment=25,
        )

        # Create a second user, kingdom, and conspicuously numbered turn. The
        # value 99 makes accidental cross-user leakage easy to recognise.
        other_user = User.objects.create_user(
            username="morgana"
        )

        other_kingdom = Kingdom.objects.create(
            owner=other_user,
            name="Dark Realm",
            ruler_name="Morgana",
            slug="dark-realm",
        )

        TurnHistory.objects.create(
            kingdom=other_kingdom,
            turn_number=99,
            population=1000,
            treasury=500,
            food=1000,
            happiness=50,
            stability=50,
            army_size=100,
            army_quality=1,
            a_eff=1,
            infra=1,
            tax_rate=20,
            agriculture_investment=25,
            infrastructure_investment=25,
            military_investment=25,
            welfare_investment=25,
        )

        response = self.client.get(reverse("turn_history"))

        self.assertEqual(response.status_code, 200)

        # The expected queryset uses the Kingdom.history reverse relationship
        # and the same descending turn-number ordering as the view.
        self.assertEqual(
            list(response.context["turns"]),
            list(
                kingdom.history.order_by("-turn_number")
            ),
        )

    def test_delete_kingdom_requires_exact_confirmation(self):
        """Confirm that an inexact phrase does not delete the kingdom."""
        kingdom = self.create_kingdom()

        response = self.client.post(
            reverse("delete_kingdom"),
            {"confirmation": "delete kingdom"},
        )

        # The deletion page is rendered again rather than redirecting.
        self.assertEqual(response.status_code, 200)

        # Database existence is the authoritative assertion that no destructive
        # side effect occurred.
        self.assertTrue(
            Kingdom.objects.filter(pk=kingdom.pk).exists()
        )

    def test_delete_kingdom_removes_it_after_confirmation(self):
        """Confirm that the exact phrase permanently deletes the kingdom."""
        kingdom = self.create_kingdom()

        response = self.client.post(
            reverse("delete_kingdom"),
            {"confirmation": "DELETE KINGDOM"},
        )

        # The current production view renders a success response with status 200
        # after deletion rather than issuing a redirect.
        self.assertEqual(response.status_code, 200)

        # Kingdom deletion also triggers configured cascades for related records,
        # including the one-to-one TurnLimit created by this test helper.
        self.assertFalse(
            Kingdom.objects.filter(pk=kingdom.pk).exists()
        )