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

# Create your tests here.


class PaymentsTestMixin:
    def create_user(self, username="ruler", email="ruler@example.com"):
        return User.objects.create_user(
            username=username,
            email=email,
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

    def create_turn_limit(self, kingdom, **overrides):
        defaults = {
            "daily_turn_limit": 3,
            "turns_remaining_today": 3,
            "cooldown_minutes": 120,
            "daily_reset_at": timezone.now(),
        }
        defaults.update(overrides)
        return TurnLimit.objects.create(kingdom=kingdom, **defaults)


class PricingViewTests(PaymentsTestMixin, TestCase):
    def test_pricing_requires_login(self):
        response = self.client.get(reverse("payments:pricing"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_logged_in_user_can_view_pricing_page(self):
        user = self.create_user()
        self.client.force_login(user)

        response = self.client.get(reverse("payments:pricing"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "payments/pricing.html")


class CheckoutSessionTests(PaymentsTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user()
        self.client.force_login(self.user)

    def test_checkout_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse("payments:checkout"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_user_without_kingdom_is_redirected_to_create_kingdom(self):
        response = self.client.get(reverse("payments:checkout"))

        self.assertRedirects(response, reverse("create_kingdom"))
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn(
            "You must create a kingdom before upgrading.",
            messages,
        )

    def test_premium_user_is_redirected_to_dashboard(self):
        self.create_kingdom(self.user, is_premium=True)

        response = self.client.get(reverse("payments:checkout"))

        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("You are already a premium ruler.", messages)

    @override_settings(STRIPE_PREMIUM_PRICE_ID="price_test_123")
    @patch("payments.views.stripe.checkout.Session.create")
    def test_checkout_session_is_created_with_expected_values(
        self,
        mock_create,
    ):
        kingdom = self.create_kingdom(self.user)
        mock_create.return_value = SimpleNamespace(
            url="https://checkout.stripe.test/session"
        )

        response = self.client.get(reverse("payments:checkout"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            "https://checkout.stripe.test/session",
        )

        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["mode"], "subscription")
        self.assertEqual(kwargs["customer_email"], self.user.email)
        self.assertEqual(
            kwargs["line_items"],
            [{"price": "price_test_123", "quantity": 1}],
        )
        self.assertEqual(
            kwargs["metadata"],
            {
                "user_id": self.user.id,
                "kingdom_id": kingdom.id,
            },
        )


class SubscriptionResultViewTests(PaymentsTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user()
        self.client.force_login(self.user)

    def test_success_view_redirects_to_dashboard_with_message(self):
        response = self.client.get(reverse("payments:success"))

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
            "Checkout completed. Your premium status will update shortly.",
            messages,
        )

    def test_cancel_view_redirects_to_pricing_with_message(self):
        response = self.client.get(reverse("payments:cancel"))

        self.assertRedirects(response, reverse("payments:pricing"))
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("Checkout cancelled.", messages)


class CheckoutCompletedHandlerTests(PaymentsTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user()
        self.kingdom = self.create_kingdom(self.user)
        self.turn_limit = self.create_turn_limit(self.kingdom)

    def test_checkout_completion_activates_premium_and_syncs_turns(self):
        handle_checkout_completed(
            {
                "metadata": {"kingdom_id": str(self.kingdom.id)},
                "customer": "cus_test_123",
                "subscription": "sub_test_123",
            }
        )

        self.kingdom.refresh_from_db()
        self.turn_limit.refresh_from_db()

        self.assertTrue(self.kingdom.is_premium)
        self.assertEqual(self.kingdom.subscription_status, "active")
        self.assertEqual(self.kingdom.stripe_customer_id, "cus_test_123")
        self.assertEqual(
            self.kingdom.stripe_subscription_id,
            "sub_test_123",
        )
        self.assertEqual(self.turn_limit.daily_turn_limit, 6)
        self.assertEqual(self.turn_limit.turns_remaining_today, 6)

    def test_checkout_completion_without_kingdom_id_does_nothing(self):
        handle_checkout_completed({"metadata": {}})

        self.kingdom.refresh_from_db()
        self.assertFalse(self.kingdom.is_premium)

    def test_checkout_completion_with_unknown_kingdom_does_nothing(self):
        handle_checkout_completed(
            {
                "metadata": {"kingdom_id": "999999"},
                "customer": "cus_missing",
                "subscription": "sub_missing",
            }
        )

        self.kingdom.refresh_from_db()
        self.assertFalse(self.kingdom.is_premium)


class SubscriptionUpdatedHandlerTests(PaymentsTestMixin, TestCase):
    def setUp(self):
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
        handle_subscription_updated(
            {"id": "sub_test_123", "status": "active"}
        )

        self.kingdom.refresh_from_db()
        self.turn_limit.refresh_from_db()

        self.assertTrue(self.kingdom.is_premium)
        self.assertEqual(self.kingdom.subscription_status, "active")
        self.assertEqual(self.turn_limit.daily_turn_limit, 6)

    def test_trialing_subscription_enables_premium(self):
        handle_subscription_updated(
            {"id": "sub_test_123", "status": "trialing"}
        )

        self.kingdom.refresh_from_db()
        self.assertTrue(self.kingdom.is_premium)
        self.assertEqual(self.kingdom.subscription_status, "trialing")

    def test_cancelled_subscription_disables_premium_and_reduces_limit(self):
        handle_subscription_updated(
            {"id": "sub_test_123", "status": "canceled"}
        )

        self.kingdom.refresh_from_db()
        self.turn_limit.refresh_from_db()

        self.assertFalse(self.kingdom.is_premium)
        self.assertEqual(self.kingdom.subscription_status, "canceled")
        self.assertEqual(self.turn_limit.daily_turn_limit, 3)
        self.assertEqual(self.turn_limit.turns_remaining_today, 3)

    def test_unknown_subscription_does_nothing(self):
        handle_subscription_updated(
            {"id": "sub_unknown", "status": "canceled"}
        )

        self.kingdom.refresh_from_db()
        self.assertTrue(self.kingdom.is_premium)
        self.assertEqual(self.kingdom.subscription_status, "active")


class StripeWebhookTests(TestCase):
    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test")
    @patch("payments.views.handle_checkout_completed")
    @patch("payments.views.stripe.Webhook.construct_event")
    def test_checkout_completed_event_calls_handler(
        self,
        mock_construct_event,
        mock_handler,
    ):
        checkout_data = {"id": "cs_test_123"}
        mock_construct_event.return_value = {
            "type": "checkout.session.completed",
            "data": {"object": checkout_data},
        }

        response = self.client.post(
            reverse("payments:webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_signature",
        )

        self.assertEqual(response.status_code, 200)
        mock_handler.assert_called_once_with(checkout_data)

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test")
    @patch("payments.views.handle_subscription_updated")
    @patch("payments.views.stripe.Webhook.construct_event")
    def test_subscription_event_calls_handler(
        self,
        mock_construct_event,
        mock_handler,
    ):
        subscription_data = {
            "id": "sub_test_123",
            "status": "active",
        }
        mock_construct_event.return_value = {
            "type": "customer.subscription.updated",
            "data": {"object": subscription_data},
        }

        response = self.client.post(
            reverse("payments:webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_signature",
        )

        self.assertEqual(response.status_code, 200)
        mock_handler.assert_called_once_with(subscription_data)

    @patch("payments.views.stripe.Webhook.construct_event")
    def test_invalid_payload_returns_400(self, mock_construct_event):
        mock_construct_event.side_effect = ValueError

        response = self.client.post(
            reverse("payments:webhook"),
            data=b"invalid",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    @patch("payments.views.stripe.Webhook.construct_event")
    def test_invalid_signature_returns_400(self, mock_construct_event):
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
    def test_sync_utility_calls_turn_limit_sync_when_present(self):
        kingdom = SimpleNamespace()
        kingdom.turn_limit = Mock()

        sync_turn_limit_for_kingdom(kingdom)

        kingdom.turn_limit.sync_with_premium_status.assert_called_once_with()

    def test_sync_utility_does_nothing_without_turn_limit(self):
        kingdom = SimpleNamespace()

        sync_turn_limit_for_kingdom(kingdom)