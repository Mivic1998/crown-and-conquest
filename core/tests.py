"""Tests for public core pages, URL routing, leaderboard behaviour, kingdom
detail access, and account deletion.

The test suite combines several testing levels:

- URL-resolution tests confirm that named routes map to the intended views.
- Public-page integration tests confirm successful responses and templates.
- Leaderboard tests verify database annotation and ordering behaviour.
- Kingdom-detail tests verify public access, owner redirection, and 404 handling.
- Account-deletion tests verify authentication, confirmation safeguards,
  destructive database behaviour, redirects, and user-facing messages.

Django's TestCase provides an isolated test database and a test client for each
test. Database changes are rolled back between tests, preventing state created
by one test from affecting another.
"""

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import resolve, reverse

from core import views
from kingdoms.models import Kingdom


class CoreTestMixin:
    """Provide reusable factories for users and their related kingdoms.

    The mixin avoids repeating the same account and Kingdom creation logic
    across leaderboard, public-detail, and account-related test classes.
    """

    def create_user(self, username="ruler"):
        """Create a standard Django user with predictable test credentials.

        Args:
            username: Username used for the account and generated email address.

        Returns:
            The newly created User instance.

        ``create_user()`` is used rather than ``User.objects.create()`` because
        it applies Django's normal password hashing and account creation logic.
        """
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="testpass123",
        )

    def create_kingdom(self, user, **overrides):
        """Create a Kingdom owned by the supplied user.

        Args:
            user: User who will own the one-to-one Kingdom record.
            **overrides: Optional Kingdom field values replacing the defaults.

        Returns:
            The newly created Kingdom.

        The helper supplies the identity fields required by Kingdom while
        allowing individual tests to override simulation values such as
        territory and population.
        """
        defaults = {
            "name": f"{user.username.title()} Kingdom",
            "ruler_name": user.username.title(),
            "slug": f"{user.username}-kingdom",
        }

        # Tests can replace defaults or supply additional Kingdom fields without
        # duplicating the full object creation call.
        defaults.update(overrides)

        return Kingdom.objects.create(owner=user, **defaults)


class CoreUrlTests(TestCase):
    """Verify that core URL names resolve to the intended view callables."""

    def test_home_url_resolves_to_home_view(self):
        """Confirm that the ``home`` URL name maps to ``core.views.home``."""
        # reverse() obtains the configured path from its URL name, while
        # resolve() maps that path back to the callable Django will execute.
        self.assertEqual(resolve(reverse("home")).func, views.home)

    def test_mechanics_url_resolves_to_mechanics_view(self):
        """Confirm that the mechanics route maps to its function-based view."""
        self.assertEqual(
            resolve(reverse("mechanics")).func,
            views.mechanics,
        )

    def test_leaderboard_url_resolves_to_leaderboard_view(self):
        """Confirm that the leaderboard route maps to its class-based view."""
        resolved_view = resolve(reverse("leaderboard")).func

        # Django exposes the original class through ``view_class`` on the
        # callable returned by ``as_view()``.
        self.assertEqual(
            resolved_view.view_class,
            views.KingdomLeaderboard,
        )

    def test_delete_account_url_resolves_to_delete_account_view(self):
        """Confirm that the account-deletion route maps to the correct view."""
        self.assertEqual(
            resolve(reverse("delete_account")).func,
            views.delete_account,
        )


class PublicPageTests(TestCase):
    """Test rendering of public pages that require no authentication."""

    def test_home_page_returns_200_and_uses_correct_template(self):
        """Confirm that the home page responds successfully with its template."""
        # The anonymous test client verifies that this page is publicly
        # accessible and does not require authentication.
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")

    def test_mechanics_page_returns_200_and_uses_correct_template(self):
        """Confirm that the game-mechanics page is publicly accessible."""
        response = self.client.get(reverse("mechanics"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/mechanics.html")


class LeaderboardTests(CoreTestMixin, TestCase):
    """Test leaderboard rendering, score annotation, and ranking order."""

    def test_leaderboard_page_returns_200(self):
        """Confirm that the public leaderboard renders successfully."""
        response = self.client.get(reverse("leaderboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/leaderboard.html")

    def test_leaderboard_calculates_realm_score(self):
        """Verify the annotated leaderboard score for a known kingdom state."""
        user = self.create_user()

        # The values are chosen so the expected formula is easy to verify:
        #
        # territory: 60 × 1,000 = 60,000
        # population: 2,500 × 0.1 = 250
        # total realm score = 60,250
        kingdom = self.create_kingdom(
            user,
            territory_count=60,
            population=2500,
        )

        response = self.client.get(reverse("leaderboard"))

        # The class-based ListView supplies ``object_list`` automatically.
        # The queryset items include the view's database-generated
        # ``realm_score`` annotation.
        listed_kingdom = next(
            item
            for item in response.context["object_list"]
            if item.pk == kingdom.pk
        )

        # This confirms that the database annotation reproduces the application's
        # intended leaderboard formula rather than merely displaying a stored
        # model field.
        self.assertEqual(listed_kingdom.realm_score, 60250)

    def test_leaderboard_orders_highest_score_first(self):
        """Verify that kingdoms are ranked by descending calculated score."""
        first_user = self.create_user("first")
        second_user = self.create_user("second")

        # The first kingdom receives a lower territory count and therefore a
        # lower score despite having the same population as the second.
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

        # Converting the queryset-like context value to a list makes positional
        # ordering assertions explicit.
        kingdoms = list(response.context["object_list"])

        self.assertEqual(kingdoms[0], higher_kingdom)
        self.assertEqual(kingdoms[1], lower_kingdom)


class KingdomDetailTests(CoreTestMixin, TestCase):
    """Test public kingdom profiles and owner-specific navigation behaviour."""

    def test_visitor_can_view_another_kingdom(self):
        """Confirm that a public visitor can view an existing kingdom profile."""
        owner = self.create_user("owner")
        kingdom = self.create_kingdom(owner)

        response = self.client.get(
            reverse("kingdom_detail", args=[kingdom.slug])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/kingdom_detail.html")

        # The view supplies the requested Kingdom as ``kingdom`` for the
        # template's ruler, statistics, crest, banner, and warfare information.
        self.assertEqual(response.context["kingdom"], kingdom)

    def test_owner_is_redirected_to_dashboard(self):
        """Confirm that an owner is redirected away from their public profile."""
        owner = self.create_user("owner")
        kingdom = self.create_kingdom(owner)

        # force_login() authenticates the client without testing the login form,
        # keeping this test focused on kingdom-detail behaviour.
        self.client.force_login(owner)

        response = self.client.get(
            reverse("kingdom_detail", args=[kingdom.slug])
        )

        # Owners manage their own kingdom through the dashboard rather than the
        # public profile intended for other visitors.
        #
        # ``fetch_redirect_response=False`` checks only the first redirect and
        # avoids requesting the dashboard as part of this assertion.
        self.assertRedirects(
            response,
            reverse("dashboard"),
            fetch_redirect_response=False,
        )

    def test_missing_kingdom_returns_404(self):
        """Confirm that an unknown slug produces an HTTP 404 response."""
        response = self.client.get(
            reverse("kingdom_detail", args=["missing-kingdom"])
        )

        # This verifies the view's object lookup failure branch instead of
        # allowing an unhandled Kingdom.DoesNotExist exception.
        self.assertEqual(response.status_code, 404)


class DeleteAccountTests(CoreTestMixin, TestCase):
    """Test the authenticated account-deletion confirmation workflow."""

    def setUp(self):
        """Create and authenticate a user before each deletion test.

        TestCase runs this method separately for every test, so deletion in one
        test does not affect the initial account state of another.
        """
        self.user = self.create_user()

        # Most tests exercise an authenticated-only view. force_login() bypasses
        # the login form and creates the required authenticated session.
        self.client.force_login(self.user)

    def test_delete_account_page_requires_login(self):
        """Confirm that anonymous users cannot open the deletion page."""
        # Remove the authenticated session established by setUp() so this test
        # exercises the view's login-required protection.
        self.client.logout()

        response = self.client.get(reverse("delete_account"))

        self.assertEqual(response.status_code, 302)

        # The redirect URL confirms that Django sends anonymous users to the
        # configured login page rather than rendering sensitive account controls.
        self.assertIn("/accounts/login/", response.url)

    def test_delete_account_page_uses_correct_template(self):
        """Confirm that an authenticated GET renders the confirmation page."""
        response = self.client.get(reverse("delete_account"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/delete_account.html")

    def test_incorrect_confirmation_does_not_delete_account(self):
        """Verify that an inexact confirmation phrase preserves the account."""
        # The submitted text deliberately differs in capitalisation from the
        # exact destructive confirmation phrase required by the view.
        response = self.client.post(
            reverse("delete_account"),
            {"confirmation": "delete account"},
        )

        # Invalid confirmation re-renders the page rather than redirecting.
        self.assertEqual(response.status_code, 200)

        # The visible error explains the exact phrase required before deletion.
        self.assertContains(
            response,
            "You must type DELETE ACCOUNT exactly to confirm.",
        )

        # The database assertion verifies the security-critical side effect:
        # the User remains present after an invalid confirmation.
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_correct_confirmation_deletes_account_and_redirects_home(self):
        """Verify successful permanent deletion and farewell messaging."""
        # Preserve the username before deletion because the User object will no
        # longer exist in the database after the view completes.
        username = self.user.username

        response = self.client.post(
            reverse("delete_account"),
            {"confirmation": "DELETE ACCOUNT"},
        )

        # Successful deletion redirects away from the protected account page.
        # assertRedirects() follows the redirect by default and verifies both
        # the redirect response and the final home-page response.
        self.assertRedirects(response, reverse("home"))

        # Querying by the original primary key confirms that the destructive
        # database operation actually occurred.
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

        # Django messages are attached to the request that produced the
        # redirect. get_messages() reads the queued user-facing notifications
        # from that request.
        messages = [
            str(message)
            for message in get_messages(response.wsgi_request)
        ]

        # The message confirms that the view preserved the username before
        # deleting the User and communicated successful completion.
        self.assertIn(
            f"Farewell, {username}. "
            "Your account has been permanently deleted.",
            messages,
        )