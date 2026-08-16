"""Tests for Stripe checkout, subscription webhooks, and premium synchronisation.

This module verifies the payment application's main responsibilities:

- protecting pricing and checkout routes with authentication;
- preventing checkout before kingdom creation or after premium activation;
- constructing Stripe Checkout sessions with the expected application data;
- displaying success and cancellation messages;
- applying completed-checkout data to Kingdom records;
- synchronising premium status with TurnLimit allowances;
- handling subscription lifecycle updates;
- validating and dispatching signed Stripe webhook events;
- isolating external Stripe calls through mocks;
- safely handling missing related TurnLimit records.

The suite combines view integration tests, direct handler tests, webhook-boundary
tests, and small utility unit tests. Stripe itself is not tested; instead, its
SDK entry points are patched so the tests verify how Crown & Conquest constructs
requests, validates events, and updates its own database state.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import stripe
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from kingdoms.models import Kingdom, TurnLimit
from payments.utils import sync_turn_limit_for_kingdom
from payments.views import (
    handle_checkout_completed,
    handle_subscription_updated,
)


class PaymentsTestMixin:
    """Provide reusable factories for payment-related users and kingdom data."""

    def create_user(self, username="ruler", email="ruler@example.com"):
        """Create a user with predictable credentials and contact details.

        Args:
            username: Username assigned to the account.
            email: Email address later supplied to Stripe Checkout.

        Returns:
            The newly created Django User.

        ``create_user()`` applies Django's normal password hashing and creates an
        account suitable for authentication through the test client.
        """
        return User.objects.create_user(
            username=username,
            email=email,
            password="testpass123",
        )

    def create_kingdom(self, user, **overrides):
        """Create a Kingdom owned by the supplied user.

        Args:
            user: User who owns the one-to-one Kingdom.
            **overrides: Optional field values replacing or extending defaults.

        Returns:
            The newly created Kingdom.

        Tests use overrides to establish premium status, Stripe identifiers, and
        subscription states without repeating the full Kingdom creation call.
        """
        defaults = {
            "name": f"{user.username.title()} Kingdom",
            "ruler_name": user.username.title(),
            "slug": f"{user.username}-kingdom",
        }

        defaults.update(overrides)

        return Kingdom.objects.create(
            owner=user,
            **defaults,
        )

    def create_turn_limit(self, kingdom, **overrides):
        """Create a TurnLimit associated with a Kingdom.

        Args:
            kingdom: Kingdom receiving the one-to-one TurnLimit.
            **overrides: Optional values replacing standard-user defaults.

        Returns:
            The newly created TurnLimit.

        The reset time is deliberately set to the current time because these
        tests focus on premium synchronisation rather than daily-reset logic.
        """
        defaults = {
            "daily_turn_limit": 3,
            "turns_remaining_today": 3,
            "cooldown_minutes": 120,
            "daily_reset_at": timezone.now(),
        }

        defaults.update(overrides)

        return TurnLimit.objects.create(
            kingdom=kingdom,
            **defaults,
        )


class PricingViewTests(PaymentsTestMixin, TestCase):
    """Test authentication and rendering for the premium pricing page."""

    def test_pricing_requires_login(self):
        """Confirm that anonymous users cannot access subscription pricing."""
        response = self.client.get(
            reverse("payments:pricing")
        )

        self.assertEqual(response.status_code, 302)

        # Verifying the login path confirms that authentication protection, not
        # an unrelated application redirect, caused the response.
        self.assertIn(
            "/accounts/login/",
            response.url,
        )

    def test_logged_in_user_can_view_pricing_page(self):
        """Confirm that an authenticated user can render the pricing page."""
        user = self.create_user()

        # force_login() bypasses the login form so this test remains focused on
        # pricing-page access and template selection.
        self.client.force_login(user)

        response = self.client.get(
            reverse("payments:pricing")
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "payments/pricing.html",
        )


class CheckoutSessionTests(PaymentsTestMixin, TestCase):
    """Test checkout permissions and Stripe Checkout session construction."""

    def setUp(self):
        """Create and authenticate a standard non-premium user."""
        self.user = self.create_user()
        self.client.force_login(self.user)

    def test_checkout_requires_login(self):
        """Confirm that anonymous users cannot create checkout sessions."""
        # Remove the authenticated session created by setUp() so this test
        # exercises the checkout view's login requirement.
        self.client.logout()

        response = self.client.get(
            reverse("payments:checkout")
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "/accounts/login/",
            response.url,
        )

    def test_user_without_kingdom_is_redirected_to_create_kingdom(self):
        """Confirm that premium checkout requires an existing Kingdom."""
        response = self.client.get(
            reverse("payments:checkout")
        )

        self.assertRedirects(
            response,
            reverse("create_kingdom"),
        )

        # Django messages survive the redirect and explain why checkout was
        # refused.
        messages = [
            str(message)
            for message in get_messages(response.wsgi_request)
        ]

        self.assertIn(
            "You must create a kingdom before upgrading.",
            messages,
        )

    def test_premium_user_is_redirected_to_dashboard(self):
        """Confirm that an already-premium kingdom cannot start checkout again."""
        self.create_kingdom(
            self.user,
            is_premium=True,
        )

        response = self.client.get(
            reverse("payments:checkout")
        )

        # The redirect target is sufficient here; avoiding the follow-up request
        # keeps the test focused on the checkout guard.
        self.assertRedirects(
            response,
            reverse("dashboard"),
            fetch_redirect_response=False,
        )

        messages = [
            str(message)
            for message in get_messages(response.wsgi_request)
        ]

        self.assertIn(
            "You are already a premium ruler.",
            messages,
        )

    @override_settings(
        STRIPE_PREMIUM_PRICE_ID="price_test_123"
    )
    @patch(
        "payments.views.stripe.checkout.Session.create"
    )
    def test_checkout_session_is_created_with_expected_values(
        self,
        mock_create,
    ):
        """Verify the exact Stripe Checkout request generated by the view."""
        kingdom = self.create_kingdom(self.user)

        # Return a lightweight object matching the portion of Stripe's Session
        # response consumed by the view. No real network request is performed.
        mock_create.return_value = SimpleNamespace(
            url="https://checkout.stripe.test/session"
        )

        response = self.client.get(
            reverse("payments:checkout")
        )

        # Stripe's hosted checkout URL is returned as an HTTP redirect.
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            "https://checkout.stripe.test/session",
        )

        # Inspect the keyword arguments passed to the patched SDK boundary. This
        # tests Crown & Conquest's Stripe configuration rather than Stripe itself.
        kwargs = mock_create.call_args.kwargs

        self.assertEqual(
            kwargs["mode"],
            "subscription",
        )

        self.assertEqual(
            kwargs["customer_email"],
            self.user.email,
        )

        self.assertEqual(
            kwargs["line_items"],
            [
                {
                    "price": "price_test_123",
                    "quantity": 1,
                }
            ],
        )

        # Metadata allows a later webhook to identify the correct local account
        # and Kingdom without trusting browser-submitted ownership information.
        self.assertEqual(
            kwargs["metadata"],
            {
                "user_id": self.user.id,
                "kingdom_id": kingdom.id,
            },
        )


class SubscriptionResultViewTests(PaymentsTestMixin, TestCase):
    """Test post-checkout success and cancellation redirect pages."""

    def setUp(self):
        """Create and authenticate a user for result-view requests."""
        self.user = self.create_user()
        self.client.force_login(self.user)

    def test_success_view_redirects_to_dashboard_with_message(self):
        """Confirm that checkout success returns the user to the dashboard."""
        response = self.client.get(
            reverse("payments:success")
        )

        self.assertRedirects(
            response,
            reverse("dashboard"),
            fetch_redirect_response=False,
        )

        messages = [
            str(message)
            for message in get_messages(response.wsgi_request)
        ]

        # The message correctly explains that premium activation is asynchronous
        # and will occur only after Stripe's signed webhook is processed.
        self.assertIn(
            (
                "Checkout completed. Your premium status "
                "will update shortly."
            ),
            messages,
        )

    def test_cancel_view_redirects_to_pricing_with_message(self):
        """Confirm that cancelled checkout returns to the pricing page."""
        response = self.client.get(
            reverse("payments:cancel")
        )

        self.assertRedirects(
            response,
            reverse("payments:pricing"),
        )

        messages = [
            str(message)
            for message in get_messages(response.wsgi_request)
        ]

        self.assertIn(
            "Checkout cancelled.",
            messages,
        )


class CheckoutCompletedHandlerTests(PaymentsTestMixin, TestCase):
    """Test database changes performed after successful checkout."""

    def setUp(self):
        """Create a standard Kingdom and TurnLimit before each handler test."""
        self.user = self.create_user()
        self.kingdom = self.create_kingdom(self.user)
        self.turn_limit = self.create_turn_limit(self.kingdom)

    def test_checkout_completion_activates_premium_and_syncs_turns(self):
        """Verify full premium activation from checkout-session metadata."""
        # The dictionary mirrors the Stripe object fields consumed by
        # handle_checkout_completed(). IDs are test values and trigger no SDK
        # request because the handler processes supplied event data directly.
        handle_checkout_completed(
            {
                "metadata": {
                    "kingdom_id": str(self.kingdom.id)
                },
                "customer": "cus_test_123",
                "subscription": "sub_test_123",
            }
        )

        # Reload both records because the handler persists changes to Kingdom and
        # invokes TurnLimit synchronisation as a side effect.
        self.kingdom.refresh_from_db()
        self.turn_limit.refresh_from_db()

        self.assertTrue(self.kingdom.is_premium)
        self.assertEqual(
            self.kingdom.subscription_status,
            "active",
        )
        self.assertEqual(
            self.kingdom.stripe_customer_id,
            "cus_test_123",
        )
        self.assertEqual(
            self.kingdom.stripe_subscription_id,
            "sub_test_123",
        )

        # Premium entitlement raises both the configured daily maximum and the
        # current remaining allowance to six.
        self.assertEqual(
            self.turn_limit.daily_turn_limit,
            6,
        )
        self.assertEqual(
            self.turn_limit.turns_remaining_today,
            6,
        )

    def test_checkout_completion_without_kingdom_id_does_nothing(self):
        """Confirm that missing metadata cannot activate an arbitrary Kingdom."""
        handle_checkout_completed(
            {"metadata": {}}
        )

        self.kingdom.refresh_from_db()

        # The local record remains unchanged because the event cannot be mapped
        # safely to a Kingdom.
        self.assertFalse(self.kingdom.is_premium)

    def test_checkout_completion_with_unknown_kingdom_does_nothing(self):
        """Confirm that unrecognised Kingdom metadata is ignored safely."""
        handle_checkout_completed(
            {
                "metadata": {
                    "kingdom_id": "999999"
                },
                "customer": "cus_missing",
                "subscription": "sub_missing",
            }
        )

        self.kingdom.refresh_from_db()

        # The existing test Kingdom must not be updated when the metadata points
        # at a record that does not exist.
        self.assertFalse(self.kingdom.is_premium)


class SubscriptionUpdatedHandlerTests(PaymentsTestMixin, TestCase):
    """Test premium entitlement changes from subscription-status events."""

    def setUp(self):
        """Create an active premium Kingdom and premium TurnLimit."""
        self.user = self.create_user()

        self.kingdom = self.create_kingdom(
            self.user,
            is_premium=True,
            stripe_subscription_id="sub_test_123",
            subscription_status="active",
        )

        self.turn_limit = self.create_turn_limit(
            self.kingdom,
            daily_turn_limit=6,
            turns_remaining_today=6,
        )

    def test_active_subscription_keeps_premium_enabled(self):
        """Confirm that an active subscription preserves premium access."""
        handle_subscription_updated(
            {
                "id": "sub_test_123",
                "status": "active",
            }
        )

        self.kingdom.refresh_from_db()
        self.turn_limit.refresh_from_db()

        self.assertTrue(self.kingdom.is_premium)
        self.assertEqual(
            self.kingdom.subscription_status,
            "active",
        )
        self.assertEqual(
            self.turn_limit.daily_turn_limit,
            6,
        )

    def test_trialing_subscription_enables_premium(self):
        """Confirm that Stripe trial status grants premium entitlement."""
        handle_subscription_updated(
            {
                "id": "sub_test_123",
                "status": "trialing",
            }
        )

        self.kingdom.refresh_from_db()

        # Trial subscriptions are treated as entitled states by the application.
        self.assertTrue(self.kingdom.is_premium)
        self.assertEqual(
            self.kingdom.subscription_status,
            "trialing",
        )

    def test_cancelled_subscription_disables_premium_and_reduces_limit(self):
        """Verify premium removal and TurnLimit reduction after cancellation."""
        handle_subscription_updated(
            {
                "id": "sub_test_123",
                "status": "canceled",
            }
        )

        self.kingdom.refresh_from_db()
        self.turn_limit.refresh_from_db()

        self.assertFalse(self.kingdom.is_premium)
        self.assertEqual(
            self.kingdom.subscription_status,
            "canceled",
        )

        # Synchronisation restores the standard allowance and prevents a former
        # premium Kingdom from retaining six turns after cancellation.
        self.assertEqual(
            self.turn_limit.daily_turn_limit,
            3,
        )
        self.assertEqual(
            self.turn_limit.turns_remaining_today,
            3,
        )

    def test_unknown_subscription_does_nothing(self):
        """Confirm that an unmatched Stripe subscription cannot alter a Kingdom."""
        handle_subscription_updated(
            {
                "id": "sub_unknown",
                "status": "canceled",
            }
        )

        self.kingdom.refresh_from_db()

        # The event ID does not match the stored subscription, so existing
        # entitlement and status remain unchanged.
        self.assertTrue(self.kingdom.is_premium)
        self.assertEqual(
            self.kingdom.subscription_status,
            "active",
        )


class StripeWebhookTests(TestCase):
    """Test webhook signature handling and event dispatch boundaries."""

    @override_settings(
        STRIPE_WEBHOOK_SECRET="whsec_test"
    )
    @patch(
        "payments.views.handle_checkout_completed"
    )
    @patch(
        "payments.views.stripe.Webhook.construct_event"
    )
    def test_checkout_completed_event_calls_handler(
        self,
        mock_construct_event,
        mock_handler,
    ):
        """Confirm that a verified checkout event reaches its handler."""
        checkout_data = {
            "id": "cs_test_123"
        }

        # construct_event() normally verifies the raw payload against Stripe's
        # signature. The mock supplies an already verified event object.
        mock_construct_event.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": checkout_data
            },
        }

        response = self.client.post(
            reverse("payments:webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_signature",
        )

        self.assertEqual(response.status_code, 200)

        # The handler is patched at payments.views because the webhook view calls
        # the name imported and resolved in that module.
        mock_handler.assert_called_once_with(
            checkout_data
        )

    @override_settings(
        STRIPE_WEBHOOK_SECRET="whsec_test"
    )
    @patch(
        "payments.views.handle_subscription_updated"
    )
    @patch(
        "payments.views.stripe.Webhook.construct_event"
    )
    def test_subscription_event_calls_handler(
        self,
        mock_construct_event,
        mock_handler,
    ):
        """Confirm that a verified subscription event reaches its handler."""
        subscription_data = {
            "id": "sub_test_123",
            "status": "active",
        }

        mock_construct_event.return_value = {
            "type": "customer.subscription.updated",
            "data": {
                "object": subscription_data
            },
        }

        response = self.client.post(
            reverse("payments:webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_signature",
        )

        self.assertEqual(response.status_code, 200)

        mock_handler.assert_called_once_with(
            subscription_data
        )

    @patch(
        "payments.views.stripe.Webhook.construct_event"
    )
    def test_invalid_payload_returns_400(
        self,
        mock_construct_event,
    ):
        """Confirm that malformed webhook payloads receive HTTP 400."""
        # Stripe's SDK raises ValueError when the raw body cannot be parsed into
        # an event. The view should reject the request without dispatching it.
        mock_construct_event.side_effect = ValueError

        response = self.client.post(
            reverse("payments:webhook"),
            data=b"invalid",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    @patch(
        "payments.views.stripe.Webhook.construct_event"
    )
    def test_invalid_signature_returns_400(
        self,
        mock_construct_event,
    ):
        """Confirm that requests failing signature verification are rejected."""
        # Reproduce the exception type raised by Stripe when the payload and
        # signature do not validate against the configured webhook secret.
        mock_construct_event.side_effect = (
            stripe.error.SignatureVerificationError(
                "Invalid signature",
                "test_signature",
            )
        )

        response = self.client.post(
            reverse("payments:webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_signature",
        )

        self.assertEqual(response.status_code, 400)


class PaymentUtilityTests(TestCase):
    """Test defensive synchronisation of Kingdom TurnLimit records."""

    def test_sync_utility_calls_turn_limit_sync_when_present(self):
        """Confirm that the utility delegates to an existing TurnLimit."""
        # SimpleNamespace provides a lightweight Kingdom-like object, while Mock
        # supplies the related object and records method calls.
        kingdom = SimpleNamespace()
        kingdom.turn_limit = Mock()

        sync_turn_limit_for_kingdom(kingdom)

        kingdom.turn_limit.sync_with_premium_status.assert_called_once_with()

    def test_sync_utility_does_nothing_without_turn_limit(self):
        """Confirm that a missing related TurnLimit is handled without error."""
        # This object deliberately has no turn_limit attribute. The test passes
        # if the utility returns normally without raising an exception.
        kingdom = SimpleNamespace()

        sync_turn_limit_for_kingdom(kingdom)