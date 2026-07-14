from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import resolve, reverse

from core import views
from kingdoms.models import Kingdom

# Create your tests here.

class CoreTestMixin:
    def create_user(self, username="ruler"):
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="testpass123",
        )

    def create_kingdom(self, user, **overrides):
        defaults = {
            "name": f"{user.username.title()} Kingdom",
            "ruler_name": user.username.title(),
            "slug": f"{user.username}-kingdom",
        }
        defaults.update(overrides)
        return Kingdom.objects.create(owner=user, **defaults)


class CoreUrlTests(TestCase):
    def test_home_url_resolves_to_home_view(self):
        self.assertEqual(resolve(reverse("home")).func, views.home)

    def test_mechanics_url_resolves_to_mechanics_view(self):
        self.assertEqual(
            resolve(reverse("mechanics")).func,
            views.mechanics,
        )

    def test_leaderboard_url_resolves_to_leaderboard_view(self):
        resolved_view = resolve(reverse("leaderboard")).func

        self.assertEqual(
            resolved_view.view_class,
            views.KingdomLeaderboard,
        )

    def test_delete_account_url_resolves_to_delete_account_view(self):
        self.assertEqual(
            resolve(reverse("delete_account")).func,
            views.delete_account,
        )


class PublicPageTests(TestCase):
    def test_home_page_returns_200_and_uses_correct_template(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")

    def test_mechanics_page_returns_200_and_uses_correct_template(self):
        response = self.client.get(reverse("mechanics"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/mechanics.html")


class LeaderboardTests(CoreTestMixin, TestCase):
    def test_leaderboard_page_returns_200(self):
        response = self.client.get(reverse("leaderboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/leaderboard.html")

    def test_leaderboard_calculates_realm_score(self):
        user = self.create_user()
        kingdom = self.create_kingdom(
            user,
            territory_count=60,
            population=2500,
        )

        response = self.client.get(reverse("leaderboard"))
        listed_kingdom = next(
            item
            for item in response.context["object_list"]
            if item.pk == kingdom.pk
        )

        self.assertEqual(listed_kingdom.realm_score, 60250)

    def test_leaderboard_orders_highest_score_first(self):
        first_user = self.create_user("first")
        second_user = self.create_user("second")
        lower_kingdom = self.create_kingdom(
            first_user,
            territory_count=40,
            population=1000,
        )
        higher_kingdom = self.create_kingdom(
            second_user,
            territory_count=70,
            population=1000,
        )

        response = self.client.get(reverse("leaderboard"))
        kingdoms = list(response.context["object_list"])

        self.assertEqual(kingdoms[0], higher_kingdom)
        self.assertEqual(kingdoms[1], lower_kingdom)


class KingdomDetailTests(CoreTestMixin, TestCase):
    def test_visitor_can_view_another_kingdom(self):
        owner = self.create_user("owner")
        kingdom = self.create_kingdom(owner)

        response = self.client.get(
            reverse("kingdom_detail", args=[kingdom.slug])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/kingdom_detail.html")
        self.assertEqual(response.context["kingdom"], kingdom)

    def test_owner_is_redirected_to_dashboard(self):
        owner = self.create_user("owner")
        kingdom = self.create_kingdom(owner)
        self.client.force_login(owner)

        response = self.client.get(
            reverse("kingdom_detail", args=[kingdom.slug])
        )

        self.assertRedirects(
            response,
            reverse("dashboard"),
            fetch_redirect_response=False,
        )

    def test_missing_kingdom_returns_404(self):
        response = self.client.get(
            reverse("kingdom_detail", args=["missing-kingdom"])
        )

        self.assertEqual(response.status_code, 404)


class DeleteAccountTests(CoreTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user()
        self.client.force_login(self.user)

    def test_delete_account_page_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse("delete_account"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_delete_account_page_uses_correct_template(self):
        response = self.client.get(reverse("delete_account"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/delete_account.html")

    def test_incorrect_confirmation_does_not_delete_account(self):
        response = self.client.post(
            reverse("delete_account"),
            {"confirmation": "delete account"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "You must type DELETE ACCOUNT exactly to confirm.",
        )
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_correct_confirmation_deletes_account_and_redirects_home(self):
        username = self.user.username

        response = self.client.post(
            reverse("delete_account"),
            {"confirmation": "DELETE ACCOUNT"},
        )

        self.assertRedirects(response, reverse("home"))
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

        messages = [
            str(message)
            for message in get_messages(response.wsgi_request)
        ]
        self.assertIn(
            f"Farewell, {username}. "
            "Your account has been permanently deleted.",
            messages,
        )