from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import KingdomSettingsForm, PolicyForm
from .models import Kingdom, TurnHistory, TurnLimit
from .utils import next_midnight

# Create your tests here.

class KingdomModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="arthur", password="testpass123"
        )
        self.kingdom = Kingdom.objects.create(
            owner=self.user,
            name="Camelot",
            ruler_name="Arthur",
            slug="camelot",
        )

    def test_string_method_returns_kingdom_name(self):
        self.assertEqual(str(self.kingdom), "Camelot")

    def test_leaderboard_score_uses_territory_and_population(self):
        self.kingdom.territory_count = 60
        self.kingdom.population = 2000
        self.assertEqual(self.kingdom.leaderboard_score, 60200)

    def test_wolf_crest_unlocks_at_required_score(self):
        self.kingdom.territory_count = 150
        self.kingdom.population = 0
        self.assertTrue(self.kingdom.has_wolf_crest_unlocked)

    def test_refresh_war_availability_sets_future_expiry(self):
        before = timezone.now()
        self.kingdom.refresh_war_availability(hours=6)
        self.kingdom.refresh_from_db()

        self.assertIsNotNone(self.kingdom.last_active_at)
        self.assertGreater(self.kingdom.war_available_until, before)
        self.assertTrue(self.kingdom.is_available_for_war())


class TurnLimitModelTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            username="guinevere", password="testpass123"
        )
        self.kingdom = Kingdom.objects.create(
            owner=user,
            name="Avalon",
            ruler_name="Guinevere",
            slug="avalon",
        )
        self.turn_limit = TurnLimit.objects.create(
            kingdom=self.kingdom,
            daily_turn_limit=3,
            turns_remaining_today=3,
            cooldown_minutes=120,
            daily_reset_at=next_midnight(),
        )

    def test_free_kingdom_has_three_daily_turns(self):
        self.assertEqual(self.turn_limit.premium_daily_limit(), 3)

    def test_premium_kingdom_has_six_daily_turns(self):
        self.kingdom.is_premium = True
        self.kingdom.save(update_fields=["is_premium"])
        self.assertEqual(self.turn_limit.premium_daily_limit(), 6)

    def test_use_turn_reduces_turns_and_starts_cooldown(self):
        self.turn_limit.use_turn()
        self.turn_limit.refresh_from_db()

        self.assertEqual(self.turn_limit.turns_remaining_today, 2)
        self.assertIsNotNone(self.turn_limit.last_turn_taken_at)
        self.assertTrue(self.turn_limit.cooldown_active())
        self.assertFalse(self.turn_limit.can_take_turn())

    def test_refresh_daily_turns_resets_expired_limit(self):
        self.turn_limit.turns_remaining_today = 0
        self.turn_limit.daily_reset_at = timezone.now() - timedelta(minutes=1)
        self.turn_limit.save()

        self.turn_limit.refresh_daily_turns()
        self.turn_limit.refresh_from_db()

        self.assertEqual(self.turn_limit.turns_remaining_today, 3)
        self.assertGreater(self.turn_limit.daily_reset_at, timezone.now())


class PolicyFormTests(TestCase):
    def valid_data(self):
        return {
            "tax_rate": 20,
            "agriculture_investment": 25,
            "infrastructure_investment": 25,
            "military_investment": 25,
            "welfare_investment": 25,
        }

    def test_valid_policy_form(self):
        self.assertTrue(PolicyForm(data=self.valid_data()).is_valid())

    def test_tax_rate_must_be_between_zero_and_fifty(self):
        data = self.valid_data()
        data["tax_rate"] = 60
        form = PolicyForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("tax_rate", form.errors)

    def test_investments_must_total_one_hundred(self):
        data = self.valid_data()
        data["welfare_investment"] = 10
        form = PolicyForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn(
            "Agriculture, infrastructure, military, and welfare investments must total 100.",
            form.non_field_errors(),
        )


class KingdomSettingsFormTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="lancelot")
        self.kingdom = Kingdom.objects.create(
            owner=user,
            name="Joyous Gard",
            ruler_name="Lancelot",
            slug="joyous-gard",
        )

    def test_free_user_cannot_edit_premium_appearance_fields(self):
        form = KingdomSettingsForm(
            instance=self.kingdom, kingdom=self.kingdom
        )

        self.assertNotIn("banner_colour", form.fields)
        self.assertNotIn("crest", form.fields)

    def test_locked_wolf_crest_is_not_offered_to_premium_user(self):
        self.kingdom.is_premium = True
        self.kingdom.save(update_fields=["is_premium"])
        form = KingdomSettingsForm(
            instance=self.kingdom, kingdom=self.kingdom
        )

        crest_values = [value for value, _ in form.fields["crest"].choices]
        self.assertNotIn("wolf", crest_values)


class KingdomViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="merlin", password="testpass123"
        )
        self.client.login(username="merlin", password="testpass123")

    def create_kingdom(self, **overrides):
        data = {
            "owner": self.user,
            "name": "Albion",
            "ruler_name": "Merlin",
            "slug": "albion",
        }
        data.update(overrides)
        kingdom = Kingdom.objects.create(**data)
        limit = 6 if kingdom.is_premium else 3
        TurnLimit.objects.create(
            kingdom=kingdom,
            daily_turn_limit=limit,
            turns_remaining_today=limit,
            daily_reset_at=next_midnight(),
        )
        return kingdom

    def test_create_kingdom_creates_kingdom_and_turn_limit(self):
        response = self.client.post(
            reverse("create_kingdom"), {"name": "Albion"}
        )

        self.assertRedirects(response, reverse("dashboard"))
        kingdom = Kingdom.objects.get(owner=self.user)
        self.assertEqual(kingdom.ruler_name, "merlin")
        self.assertEqual(kingdom.slug, "albion")
        self.assertTrue(TurnLimit.objects.filter(kingdom=kingdom).exists())

    def test_existing_owner_is_redirected_from_create_page(self):
        self.create_kingdom()
        response = self.client.get(reverse("create_kingdom"))
        self.assertRedirects(response, reverse("dashboard"))

    def test_dashboard_redirects_user_without_kingdom(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("create_kingdom"))

    def test_dashboard_displays_owned_kingdom(self):
        kingdom = self.create_kingdom()
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["kingdom"], kingdom)
        self.assertContains(response, "Albion")

    def test_turn_history_only_contains_current_users_turns(self):
        kingdom = self.create_kingdom()
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
        other_user = User.objects.create_user(username="morgana")
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
        self.assertEqual(
            list(response.context["turns"]),
            list(kingdom.history.order_by("-turn_number")),
        )

    def test_delete_kingdom_requires_exact_confirmation(self):
        kingdom = self.create_kingdom()

        response = self.client.post(
            reverse("delete_kingdom"),
            {"confirmation": "delete kingdom"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Kingdom.objects.filter(pk=kingdom.pk).exists()
        )

    def test_delete_kingdom_removes_it_after_confirmation(self):
        kingdom = self.create_kingdom()
        response = self.client.post(
            reverse("delete_kingdom"),
            {"confirmation": "DELETE KINGDOM"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Kingdom.objects.filter(pk=kingdom.pk).exists())