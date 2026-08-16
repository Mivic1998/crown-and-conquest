"""Stripe checkout, webhook, and premium-subscription views.

This module coordinates the application's payment workflow with Stripe.

Its responsibilities include:

- displaying the authenticated premium-pricing page;
- creating a hosted Stripe Checkout Session;
- redirecting users after successful or cancelled checkout;
- receiving and verifying Stripe webhook events;
- activating or removing premium kingdom status;
- synchronising premium status with the kingdom's daily turn allowance.

Stripe remains the authoritative source for subscription events. Returning to
the success page does not directly grant premium access; the application waits
for a verified webhook before updating the Kingdom record.
"""

from django.shortcuts import render
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

# Configure the Stripe SDK once when this module is imported. Subsequent Stripe
# API calls, including Checkout Session creation, use this secret key.
stripe.api_key = settings.STRIPE_SECRET_KEY #Gives your Django backend permission to communicate with Stripe account.

from kingdoms.models import Kingdom
from .utils import sync_turn_limit_for_kingdom


@login_required
def pricing(request):
    """Display the premium subscription page.

    Authentication is required because the pricing template checks the current
    user's kingdom and posts to the authenticated checkout workflow.

    Args:
        request: The authenticated Django HTTP request.

    Returns:
        A rendered ``payments/pricing.html`` response.
    """
    return render(
        request,
        "payments/pricing.html",
    )


@login_required
def create_checkout_session(request):
    """Create a Stripe-hosted subscription Checkout Session.

    The player must own a kingdom and must not already be premium. Stripe
    receives the configured recurring price, the user's email address,
    application return URLs, and internal identifiers stored as metadata.

    Premium status is not updated here. It is updated later by a verified
    Stripe webhook after checkout completes.

    Args:
        request: The authenticated Django HTTP request.

    Returns:
        A redirect to Stripe Checkout, kingdom creation, or the dashboard.
    """
    # A subscription is attached to a Kingdom rather than directly to the User,
    # so checkout cannot begin until kingdom creation has been completed.
    if not hasattr(request.user, "kingdom"):
        messages.error(
            request,
            "You must create a kingdom before upgrading.",
        )
        return redirect("create_kingdom")

    kingdom = request.user.kingdom

    # Prevent duplicate subscription attempts through the normal checkout URL.
    # The server checks this even though the pricing template hides the
    # subscription button for premium users.
    if kingdom.is_premium:
        messages.info(
            request,
            "You are already a premium ruler.",
        )
        return redirect("dashboard")

    # Stripe hosts the payment interface, so Crown & Conquest does not collect
    # or store card details within its own forms or database.
    checkout_session = stripe.checkout.Session.create(#Creates a checkout page for the user
        # Subscription mode tells Stripe to create recurring billing rather
        # than a one-time payment.
        mode="subscription",

        # Restrict the current Checkout Session to card payments.
        payment_method_types=["card"],

        # Prepopulate Stripe Checkout with the authenticated user's email.
        customer_email=request.user.email,

        # The Stripe Price ID is configured externally through Django settings.
        # Quantity one represents one premium kingdom subscription.
        line_items=[
            {
                "price": settings.STRIPE_PREMIUM_PRICE_ID,#Identifies the premium subscription price configured in Stripe account
                "quantity": 1,#One premium subscription
            }
        ],

        # Stripe requires absolute return URLs. ``build_absolute_uri`` combines
        # the current site's scheme and host with Django's reversed route.
        success_url=request.build_absolute_uri(
            reverse("payments:success") #Tells stripe where to direct user when purchase has been successful, the subscription_success view
        ),
        cancel_url=request.build_absolute_uri(
            reverse("payments:cancel") #Tells stripe where to direct user when subscriprion is cancelled, the subscription_cancel view
        ),

        # Internal identifiers allow the later checkout webhook to reconnect the
        # Stripe session to the correct local user and Kingdom record.
        metadata={
            "user_id": request.user.id, 
            "kingdom_id": kingdom.id, #IDs are attached to the checkout session so that the application knows which kingdom it should make premium
        },
    )

    # Redirect the browser away from Django to Stripe's hosted checkout page.
    return redirect(checkout_session.url)


@login_required
def subscription_success(request):
    """Handle the browser return after successful Stripe Checkout.

    This view only confirms that the browser returned from Stripe. It does not
    grant premium access because browser redirects can be revisited or forged.
    Premium state is updated asynchronously through the verified webhook.

    Args:
        request: The authenticated Django HTTP request.

    Returns:
        A redirect to the dashboard with an informational success message.
    """
    # The base template renders this queued message after the redirect.
    messages.success(
        request,
        "Checkout completed. Your premium status will update shortly.",
    )
    return redirect("dashboard")


@login_required
def subscription_cancel(request):
    """Handle the browser return after checkout cancellation.

    No database state changes are required because the user did not complete
    the Stripe subscription workflow.

    Args:
        request: The authenticated Django HTTP request.

    Returns:
        A redirect back to the pricing page with an informational message.
    """
    # The base template displays this message after the redirect.
    messages.info(
        request,
        "Checkout cancelled.",
    )
    return redirect("payments:pricing")


@csrf_exempt
def stripe_webhook(request):
    """Receive and verify subscription events sent directly by Stripe.

    CSRF protection is disabled because Stripe is an external service and
    cannot provide Django's CSRF token. Security instead comes from validating
    the ``Stripe-Signature`` header against the configured webhook secret.

    Supported events are delegated to dedicated handler functions. Unknown but
    valid Stripe events are acknowledged with HTTP 200 and otherwise ignored.

    Args:
        request: The incoming Stripe webhook HTTP request.

    Returns:
        HTTP 200 for a valid processed or ignored event, or HTTP 400 when the
        payload or signature cannot be verified.
    """
    # The exact raw request body must be passed to Stripe. Parsing and rebuilding
    # it first could alter the payload and invalidate signature verification.
    payload = request.body

    # Django exposes the ``Stripe-Signature`` HTTP header through META using the
    # ``HTTP_STRIPE_SIGNATURE`` key.
    signature = request.META.get("HTTP_STRIPE_SIGNATURE")

    try:
        # Stripe validates both the payload structure and cryptographic
        # signature before the application trusts any included event data.
        event = stripe.Webhook.construct_event(
            payload,
            signature,
            settings.STRIPE_WEBHOOK_SECRET,
        )#Verifies that the incoming message from Stripe is genuine using the webhook secret
    except ValueError:
        # A malformed or unparseable payload is rejected.
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        # A correctly shaped request with an invalid signature is also rejected.
        return HttpResponse(status=400)#Server will not process request if payload is broken or signature is invalid

    event_type = event["type"]#What happened
    data_object = event["data"]["object"]#Details about what happened

    # Checkout completion contains the metadata needed to connect a newly
    # created Stripe customer and subscription to a local Kingdom.
    if event_type == "checkout.session.completed":
        handle_checkout_completed(data_object)#Refers django to view which processes a completed checkout

    # Later subscription lifecycle events identify the local kingdom through
    # its stored Stripe subscription ID.
    elif event_type in [
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ]:
        handle_subscription_updated(data_object)

    # Stripe expects a successful response so it knows that the event was
    # received. Returning 200 also acknowledges valid event types not used here.
    return HttpResponse(status=200)


def handle_checkout_completed(session):
    """Activate premium access following a completed checkout session.

    The kingdom ID is read from the trusted, signature-verified Stripe session
    metadata. Stripe customer and subscription identifiers are saved locally so
    later lifecycle events can locate the same kingdom.

    Args:
        session: The Stripe Checkout Session object supplied by the webhook.

    Returns:
        ``None``. Missing metadata or an unknown kingdom is handled safely
        without raising an exception.

    Side effects:
        - Updates Stripe identifiers on a Kingdom.
        - Marks the kingdom premium and its subscription active.
        - Synchronises the related TurnLimit record.
    """
    # Metadata was added when the Checkout Session was created. ``get`` calls
    # avoid exceptions if Stripe sends an unexpected or incomplete object.
    kingdom_id = session.get("metadata", {}).get("kingdom_id")#Once checkout is completed, the kingdom ID associated with the session is retrieved

    # Without a local kingdom identifier, the application cannot safely apply
    # the subscription to any player.
    if not kingdom_id:
        return

    # ``first`` returns None rather than raising an exception if the kingdom was
    # deleted between checkout creation and webhook delivery.
    kingdom = Kingdom.objects.filter(
        id=kingdom_id
    ).first()#The Kingdom associated with the ID from the metadata is retrieved

    if not kingdom:
        return

    # Persist Stripe's customer and subscription references for future webhook
    # events such as cancellation or status changes.
    kingdom.stripe_customer_id = session.get("customer")
    kingdom.stripe_subscription_id = session.get("subscription")

    # Checkout completion is treated as an active subscription in this handler.
    kingdom.subscription_status = "active"
    kingdom.is_premium = True #Kingdom is made premium

    # ``update_fields`` limits the database write to fields changed by the
    # checkout workflow.
    kingdom.save(
        update_fields=[
            "stripe_customer_id",
            "stripe_subscription_id",
            "subscription_status",
            "is_premium",
        ]
    )

    # Premium kingdoms receive six daily turns instead of three. The utility
    # safely does nothing when a related TurnLimit record does not exist.
    sync_turn_limit_for_kingdom(kingdom)


def handle_subscription_updated(subscription):
    """Synchronise a kingdom with a Stripe subscription lifecycle event.

    Stripe sends this handler subscription-created, subscription-updated, and
    subscription-deleted event objects. The stored Stripe subscription ID is
    used to locate the associated Kingdom.

    Only ``active`` and ``trialing`` statuses grant premium access. All other
    statuses remove premium access and cause the turn limit to be synchronised
    with the standard allowance.

    Args:
        subscription: The Stripe Subscription object supplied by the webhook.

    Returns:
        ``None``. Unknown subscriptions are ignored safely.

    Side effects:
        - Updates the kingdom's subscription status.
        - Enables or disables premium access.
        - Synchronises the related TurnLimit record.
    """
    stripe_subscription_id = subscription.get("id")
    status = subscription.get("status")

    # Later Stripe subscription events do not necessarily include the Checkout
    # metadata, so the stored subscription ID is the local lookup key.
    kingdom = Kingdom.objects.filter(
        stripe_subscription_id=stripe_subscription_id
    ).first()

    # The subscription may belong to another environment or to a kingdom that
    # has since been deleted. Such events are acknowledged but ignored.
    if not kingdom:
        return

    # Preserve the exact status supplied by Stripe for account state and
    # debugging visibility.
    kingdom.subscription_status = status

    # Only currently active or trial subscriptions unlock premium features.
    # Statuses such as canceled, unpaid, past_due, or incomplete evaluate false.
    kingdom.is_premium = status in [
        "active",
        "trialing",
    ] #If subscription has been deleted, boolean will be set to false and premium priveleges will be revoked.

    kingdom.save(
        update_fields=[
            "subscription_status",
            "is_premium",
        ]
    )

    # Update the associated daily allowance to six or three according to the
    # newly stored premium state.
    sync_turn_limit_for_kingdom(kingdom)