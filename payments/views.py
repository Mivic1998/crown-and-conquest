from django.shortcuts import render
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
stripe.api_key = settings.STRIPE_SECRET_KEY
from kingdoms.models import Kingdom
from .utils import sync_turn_limit_for_kingdom

# Create your views here.

@login_required
def pricing(request):
    return render(request, "payments/pricing.html")


@login_required
def create_checkout_session(request):
    if not hasattr(request.user, "kingdom"):
        messages.error(request, "You must create a kingdom before upgrading.")
        return redirect("create_kingdom")

    kingdom = request.user.kingdom

    if kingdom.is_premium:
        messages.info(request, "You are already a premium ruler.")
        return redirect("dashboard")

    checkout_session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        customer_email=request.user.email,
        line_items=[
            {
                "price": settings.STRIPE_PREMIUM_PRICE_ID,
                "quantity": 1,
            }
        ],
        success_url=request.build_absolute_uri(
            reverse("payments:success")
        ),
        cancel_url=request.build_absolute_uri(
            reverse("payments:cancel")
        ),
        metadata={
            "user_id": request.user.id,
            "kingdom_id": kingdom.id,
        },
    )

    return redirect(checkout_session.url)


@login_required
def subscription_success(request):
    messages.success(
        request,
        "Checkout completed. Your premium status will update shortly.",
    )
    return redirect("dashboard")


@login_required
def subscription_cancel(request):
    messages.info(request, "Checkout cancelled.")
    return redirect("payments:pricing")


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    signature = request.META.get("HTTP_STRIPE_SIGNATURE")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            signature,
            settings.STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        return HttpResponse(status=400)

    event_type = event["type"]
    data_object = event["data"]["object"]

    if event_type == "checkout.session.completed":
        handle_checkout_completed(data_object)

    elif event_type in [
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ]:
        handle_subscription_updated(data_object)

    return HttpResponse(status=200)

def handle_checkout_completed(session):
    kingdom_id = session.get("metadata", {}).get("kingdom_id")

    if not kingdom_id:
        return

    kingdom = Kingdom.objects.filter(id=kingdom_id).first()

    if not kingdom:
        return

    kingdom.stripe_customer_id = session.get("customer")
    kingdom.stripe_subscription_id = session.get("subscription")
    kingdom.subscription_status = "active"
    kingdom.is_premium = True

    kingdom.save(
        update_fields=[
            "stripe_customer_id",
            "stripe_subscription_id",
            "subscription_status",
            "is_premium",
        ]
    )

    sync_turn_limit_for_kingdom(kingdom)


def handle_subscription_updated(subscription):
    stripe_subscription_id = subscription.get("id")
    status = subscription.get("status")

    kingdom = Kingdom.objects.filter(
        stripe_subscription_id=stripe_subscription_id
    ).first()

    if not kingdom:
        return

    kingdom.subscription_status = status
    kingdom.is_premium = status in [
        "active",
        "trialing",
    ]

    kingdom.save(
        update_fields=[
            "subscription_status",
            "is_premium",
        ]
    )

    sync_turn_limit_for_kingdom(kingdom)