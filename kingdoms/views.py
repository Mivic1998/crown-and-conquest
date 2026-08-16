"""Views for kingdom management, turn progression, events, and statistics.

This module coordinates the principal player-facing workflows within the
``kingdoms`` application. It connects authenticated HTTP requests to forms,
simulation services, AI evaluation, database models, and Django templates.

The views intentionally avoid containing the detailed mathematical simulation.
Instead, they perform four main responsibilities:

1. Verify authentication, kingdom ownership, and feature access.
2. Validate submitted user input.
3. Call the appropriate business-logic or AI service.
4. Supply the resulting data to a template or downloadable response.

Principal workflows include:

- displaying and updating the kingdom dashboard;
- creating, configuring, and deleting kingdoms;
- processing simulation turns;
- resolving AI-assisted events;
- displaying turn and event history;
- preparing premium statistics and charts;
- exporting historical data as CSV.
"""

import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from core.ai import evaluate_event_response, evaluate_policy_decision

from .events import EVENT_EFFECTS, apply_event_response_effects
from .forms import CreateKingdomForm, KingdomSettingsForm, PolicyForm
from .models import Event, Kingdom, TurnHistory, TurnLimit
from .simulation import process_turn
from .utils import build_effect_comparison, calculate_score, next_midnight


@login_required
def dashboard(request):
    """Display the kingdom dashboard and process policy changes.

    A GET request prepares the player's current kingdom state, policy form,
    notifications, turn availability, unresolved events, and warfare updates.

    A POST request validates and saves a new policy allocation. Premium players
    also receive AI-generated council advice based on the validated policies.

    Args:
        request: The authenticated Django HTTP request.

    Returns:
        A rendered ``kingdoms/dashboard.html`` response, or a redirect to
        kingdom creation if the authenticated user does not own a kingdom.
    """
    # ``request.user.kingdom`` is a reverse one-to-one relationship. Checking
    # for it first prevents a RelatedObjectDoesNotExist exception for users who
    # have registered but have not yet entered the gameplay lifecycle.
    if not hasattr(request.user, "kingdom"):
        messages.info(
            request,
            "You need to create a kingdom before accessing the dashboard.",
        )
        return redirect("create_kingdom")

    kingdom = request.user.kingdom

    # Warfare availability depends on deadlines and cooldown timestamps.
    # Refreshing it when the dashboard opens ensures that displayed war actions
    # reflect the current time rather than stale database state.
    kingdom.refresh_war_availability() #Kingdoms are only available for war if they have been active within a certain timeframe. This method refreshes the kingdom's war availability when visiting the dashboard.

    # An unresolved event prevents the player from advancing another turn.
    # The template uses this object to display the crisis notification and a
    # link to the event-response page.
    unresolved_event = kingdom.events.filter(
        is_resolved=False, #Kingdoms with outstanding events cannot take new turns until the event is resolved, this filter checks for any unresolved events associated with the kingdom.
    ).first()

    # Turn reports remain visible in the dashboard notification area until
    # their detail pages mark them as seen.
    unseen_turns = kingdom.history.filter(
        report_seen=False, #If a turn report has not been viewed by the player, it is considered unseen. This filter retrieves all unseen turn reports for the kingdom which are displayed in the dashboard notifications.
    ).all()

    # Received and initiated wars are retrieved separately because the
    # dashboard displays different text and links for attacker and defender.
    pending_war_received = kingdom.wars_received.filter(
        status="pending_defender", #This filter retrieves wars where the kingdom is the defender and the war is pending. It allows the dashboard to display notifications for wars that require the player's response as a defender.
    ).first()

    pending_war_started = kingdom.wars_started.filter(
        status="pending_defender", #This filter retrieves wars where the kingdom is the attacker and the war is pending. It allows the player to view the war pending page of the war they initiated while it is unresolved.
    ).first()

    # Resolved battle reports are also separated according to the current
    # kingdom's role in the war. The template uses the related attacker or
    # defender name when constructing notification text.
    unseen_battle_reports_started = kingdom.wars_started.filter(
        status="resolved", 
        battle__report_seen=False,
    ).order_by("-resolved_at") #This filter retrieves battle reports for resolved wars where the kingdom was the attacker and the report has not been seen.

    unseen_battle_reports_received = kingdom.wars_received.filter(
        status="resolved",
        battle__report_seen=False,
    ).order_by("-resolved_at") #This filter retrieves battle reports for resolved wars where the kingdom was the defender and the report has not been seen.

    turn_limit = kingdom.turn_limit #Retrieves the TurnLimit object associated with the kingdom, which tracks the number of turns remaining for the day and any cooldown periods. This object is used to determine whether the player can currently take a turn.

    # Refresh the allowance before displaying it because the daily reset may
    # have passed since the player's previous request.
    turn_limit.refresh_daily_turns()

    # Remove an expired timestamp after its cooldown has ended. This prevents
    # the dashboard template and JavaScript countdown from receiving an old
    # ``cooldown_ends_at`` value.
    if not turn_limit.cooldown_active():
        turn_limit.cooldown_ends_at = None
        turn_limit.save(update_fields=["cooldown_ends_at"]) #If the cooldown period has expired or doesn't exist, the cooldown_ends_at field in the TurnLimit model is cleared to prevent the dashboard from displaying an outdated countdown timer and to allow the player to take a turn if they have remaining turns available.

    turn_blocked = False #Creates a flag which is set to False by default and changed to True if the player is blocked from taking a turn for any reason.
    turn_blocked_reason = "" #Specifies the reason for the turn being blocked if one exists. Displayed in the dashboard to inform the player why they cannot take a turn.

    # Event resolution takes priority over the ordinary turn-limit checks.
    if unresolved_event:
        turn_blocked = True
        turn_blocked_reason = (
            "You must respond to the current crisis before advancing."
        )

    elif not turn_limit.can_take_turn():
        turn_blocked = True

        if turn_limit.cooldown_active():
            turn_blocked_reason = (
                "You must wait for the turn cooldown to expire."
            )
        else:
            turn_blocked_reason = (
                "You have no turns remaining today."
            ) #This section starting from the if statement checks each condition that could block the player from taking a turn. If the player is blocked, the boolean is set to true and the player receives the appropriate messages explaining why they are unable to take a turn.

    if request.method == "POST":
        # Binding the ModelForm to the existing kingdom updates that record
        # rather than creating a second Kingdom instance.
        form = PolicyForm(
            request.POST,
            instance=kingdom,
        )

        if form.is_valid():
            kingdom = form.save()

            # The template's JavaScript displays the allocation total while the
            # form validates that all four investments equal exactly 100%.
            investment_total = (
                kingdom.agriculture_investment
                + kingdom.infrastructure_investment
                + kingdom.military_investment
                + kingdom.welfare_investment
            ) #Used for displaying the total of the four policy investments to the dashboard.

            if kingdom.is_premium:
                # Only validated form values are sent to the AI service.
                # The advice is informational and does not alter the kingdom or
                # consume a turn.
                policy_advice = evaluate_policy_decision(
                    kingdom,
                    form.cleaned_data,
                ) #If the Kingdom is premium, the validated policy allocation is sent to the AI evaluation service, which returns structured advice for the player. Stored as JSON dictionary.

                # The dashboard reads ``summary``, ``risk``, and
                # ``recommendation`` from this JSON-compatible dictionary.
                kingdom.policy_advice = policy_advice or {}
                kingdom.save(update_fields=["policy_advice"]) #Policy advice saved either as the AI-generated dictionary if advice was returned, or an empty dictionary if the AI service was unavailable.

                success_message = (
                    "Policies saved. Your premium royal council "
                    "has prepared advice."
                )
            else:
                success_message = (
                    "Policies saved. Upgrade to Premium to unlock "
                    "royal council advice."
                ) #Success message displayed after saving the policy allocation, which differs depending on whether the player has received AI council advice, which is provided if they are a premiuma account.

            # Redirect-after-POST prevents a browser refresh from resubmitting
            # the policy form.
            messages.success(request, success_message)
            return redirect("dashboard")

        # The form performs the authoritative validation, but calculating the
        # submitted value here allows the message and template to show the
        # exact incorrect total entered by the player.
        submitted_total = sum(
            int(request.POST.get(field, 0) or 0)
            for field in [
                "agriculture_investment",
                "infrastructure_investment",
                "military_investment",
                "welfare_investment",
            ]
        ) #If the form is not valid, the submitted total is calculated from the raw POST data to provide feedback to the player about the exact total they submitted.

        messages.error(
            request,
            f"Your investments currently total {submitted_total}%. "
            "They must total exactly 100% before they can be saved.",
        )

        investment_total = submitted_total 

        # The template must not present the policy allocation as turn-ready
        # when the submitted values are invalid.
        can_take_turn = False #The player can not take a turn if the submitted policy allocation is invalid, so the boolean is set to False to block the end turn button.

    else:
        # An unbound form displays the policies currently stored on the kingdom.
        form = PolicyForm(instance=kingdom)

        investment_total = (
            kingdom.agriculture_investment
            + kingdom.infrastructure_investment
            + kingdom.military_investment
            + kingdom.welfare_investment
        ) 

        # This value describes policy validity only. Turn availability itself
        # is controlled separately through ``turn_blocked``.
        can_take_turn = investment_total == 100 #The player can only take a turn if the investment total is exactly 100%, which is what this boolean is checking.

    return render(
        request,
        "kingdoms/dashboard.html",
        {
            # Used throughout the template to display the kingdom name, ruler,
            # banner, crest, premium status, current turn, leaderboard score,
            # population, treasury, food, happiness, stability, military data,
            # war record, stored policy values, and premium council advice.
            "kingdom": kingdom,

            # Supplies the tax and investment controls. The template reads each
            # field's current value and the form preserves invalid POST data so
            # the player can correct it.
            "form": form,

            # Provides remaining turns, the daily allowance, reset timestamp,
            # and cooldown timestamp. Dashboard JavaScript uses the ISO-formatted
            # times to display live countdown information.
            "turn_limit": turn_limit,

            # Controls whether the template displays the turn action as blocked.
            "turn_blocked": turn_blocked,

            # Displays the specific event, cooldown, or allowance explanation
            # beside the disabled turn action.
            "turn_blocked_reason": turn_blocked_reason,

            # Iterated in the notification panel to create links to unread
            # turn-detail reports.
            "unseen_turns": unseen_turns,

            # Displays the active crisis type and a link to its response form.
            "unresolved_event": unresolved_event,

            # Displays the incoming attacker and links the defender to the war
            # notification and response page.
            "pending_war_received": pending_war_received,

            # Displays the defender's name and links the attacker to the pending
            # war page while awaiting a response.
            "pending_war_started": pending_war_started,

            # Iterated to show unread reports for wars where this kingdom was
            # the defender.
            "unseen_battle_reports_received": (
                unseen_battle_reports_received
            ),

            # Iterated to show unread reports for wars initiated by this kingdom.
            "unseen_battle_reports_started": (
                unseen_battle_reports_started
            ),

            # Represents the sum of the four policy investments. It supports
            # immediate allocation feedback alongside the policy controls.
            "investment_total": investment_total,

            # Indicates whether the current investment allocation totals 100%.
            # The actual turn endpoint repeats all authoritative checks.
            "can_take_turn": can_take_turn,
        },
    )


@login_required
def create_kingdom(request):
    """Create a kingdom and its initial turn-limit record.

    Each authenticated account can own only one kingdom. A valid submission
    creates the kingdom, assigns ownership, generates its slug and ruler name,
    and creates the related ``TurnLimit`` required by the dashboard.

    Args:
        request: The authenticated Django HTTP request.

    Returns:
        ``kingdoms/create_kingdom.html`` with its form, or a redirect to the
        dashboard following successful creation.
    """
    # Prevent creation of a second kingdom by directly revisiting the URL.
    if hasattr(request.user, "kingdom"):
        return redirect("dashboard")

    if request.method == "POST":
        form = CreateKingdomForm(request.POST)

        if form.is_valid():
            # The model is not saved immediately because fields that should not
            # be controlled by the browser must first be assigned server-side.
            kingdom = form.save(commit=False)

            # Ownership always comes from the authenticated session, preventing
            # a user from assigning the kingdom to another account.
            kingdom.owner = request.user
            kingdom.ruler_name = request.user.username
            kingdom.slug = slugify(kingdom.name)
            kingdom.save()

            # Premium kingdoms have a larger daily allowance. New kingdoms will
            # ordinarily begin with the standard value unless premium status was
            # established through another workflow.
            daily_limit = 6 if kingdom.is_premium else 3

            # Turn limits are kept in a separate one-to-one model so timing and
            # allowance rules do not become mixed with simulation statistics.
            TurnLimit.objects.create(
                kingdom=kingdom,
                daily_turn_limit=daily_limit,
                turns_remaining_today=daily_limit,
                daily_reset_at=next_midnight(),
            )

            return redirect("dashboard")
    else:
        form = CreateKingdomForm()

    return render(
        request,
        "kingdoms/create_kingdom.html",
        {
            # Rendered through ``form.as_p`` to display the creation controls,
            # submitted values, and any validation errors.
            "form": form,
        },
    )


@login_required
@require_POST
def take_turn(request):
    """Validate and process one complete simulation turn.

    This endpoint accepts POST requests only because it mutates persistent
    gameplay state. It checks kingdom ownership, unresolved events, daily
    allowances, and cooldowns before invoking the simulation.

    The kingdom update, historical snapshot, turn consumption, and optional
    event creation are wrapped in a database transaction.

    Args:
        request: The authenticated POST request.

    Returns:
        ``kingdoms/turn_feedback.html`` after success, or a redirect with a
        warning when the turn cannot be processed.
    """
    kingdom = getattr(request.user, "kingdom", None) #Retrieves the kingdom associated with the authenticated user.

    if kingdom is None:
        return redirect("create_kingdom")

    kingdom.refresh_war_availability() #Inactive kingdoms are not available for war. This method refreshes the kingdom's war availability when taking a turn to ensure that its status is up to date.

    # This check is repeated here even though the dashboard disables the turn
    # control. A user could otherwise submit directly to this endpoint.
    if kingdom.events.filter(is_resolved=False).exists():
        messages.warning(
            request,
            "You must resolve the current crisis before advancing the realm.",
        )
        return redirect("dashboard") #Checks for any unresolved events, which will block the turn. This has already been checked in the dashboard view, but is repeated here to prevent user from bypassing the dashboard via URL manipulation.

    turn_limit = kingdom.turn_limit
    turn_limit.refresh_daily_turns() #Before checking the turn limit, the daily allowance is refreshed to ensure the player's remaining turns are up to date.

    if not turn_limit.can_take_turn():
        if turn_limit.cooldown_active():
            messages.warning(
                request,
                (
                    "You cannot take a turn at this moment. Please wait "
                    "until the cooldown period has expired."
                ),
            )
        else:
            messages.warning(
                request,
                "You have no turns remaining. Please try again tomorrow.",
            )

        return redirect("dashboard") #This block checks whether the player can take a turn based on their remaining turns and cooldown status. If they cannot, they are redirected to the dashboard with the appropriate warning message.

    # Council advice describes the proposed policies before they are processed.
    # Once a turn begins, that advice is no longer current.
    kingdom.policy_advice = {} #Council advice is cleared after the turn is processed because the kingdom has evolved and the previous advice is no longer relevant.

    # If any operation fails, all changes made inside this block are rolled
    # back. This prevents a consumed allowance without a completed turn, or a
    # completed turn without its historical record.
    with transaction.atomic(): #If any operation within this block fails, all changes made to the database are rolled back so that the kingdom is not partially updated. This ensures that the turn is either fully processed or not at all.
        event, turn = process_turn(kingdom) #Processes the turn for the kingdom using the function from simulation.py. This function updates the kingdom's state. creates a TurnHistory snapshot for record-keeping, and may generate a new event.
        turn_limit.use_turn() #TurnLimit method which decrements the remaining turns for the day and updates the cooldown timestamp in the TurnLimit model.

        if event:
            # ``process_turn`` returns an event-type key rather than creating
            # the Event record itself. This view connects it to the precise
            # TurnHistory snapshot created during the same transaction.
            data = EVENT_EFFECTS.get(event, {}) #Retrieves the event's predefined effects from the EVENT_EFFECTS dictionary from events.py using the event type returned by process_turn.

            Event.objects.create(
                kingdom=kingdom,
                turn=turn,
                turn_number=turn.turn_number,
                event_type=event,
                description=data.get("description", ""),
            ) #If an event was generated by the simulation, the database creates a new Event record associated with the kingdom and the current TurnHistory snapshot.

    return render(
        request,
        "kingdoms/turn_feedback.html",
        {
            # The template displays the completed turn number, simulation
            # statistics, army values, and the policy allocation responsible
            # for the result. Through the related ``turn.event`` object it also
            # displays any generated crisis and links to its response page.
            "turn": turn,
        },
    )


@login_required
def respond_to_event(request):
    """Display and resolve the player's current unresolved event.

    On POST, the player's written decree is submitted to the AI evaluation
    service. The structured category scores are stored, combined into a final
    score, and used to scale the predefined event effects.

    Args:
        request: The authenticated Django HTTP request.

    Returns:
        ``kingdoms/event_response.html`` for GET or invalid input, otherwise a
        redirect to the completed event report.
    """
    if not hasattr(request.user, "kingdom"):
        messages.info(
            request,
            "You need to create a kingdom before responding to an event.",
        )
        return redirect("create_kingdom") #Prevents URL manipulation by checking that the user owns a kingdom before accessing the event response page.

    # Filtering by kingdom and unresolved state enforces ownership and prevents
    # an already completed event from being processed twice.
    event = get_object_or_404(
        Event,
        kingdom=request.user.kingdom,
        is_resolved=False,
    ) #Retrieves the current unresolved event for the kingdom. If no such event exists, a 404 error is returned.

    kingdom = request.user.kingdom
    kingdom.refresh_war_availability() #Kingdom considered active if it is responding to an event, so it is refreshed to ensure that its war availability is up to date.

    if request.method == "POST":
        response = request.POST.get("response", "").strip()

        # Reject empty or whitespace-only decrees before making an external API
        # request.
        if not response:
            return render(
                request,
                "kingdoms/event_response.html",
                {
                    # Displays the event artwork, type, turn number, narrative,
                    # and the response textarea.
                    "event": event,

                    # Rendered directly beneath the form when no decree was
                    # supplied.
                    "error": "You must write a royal decree.",
                },
            )

        # The helper always returns the expected structure, using conservative
        # fallback scores if Gemini is unavailable or its response is invalid.
        ai_result = evaluate_event_response(
            event=event,
            player_response=response,
        ) #Sends the player's response for AI evaluation.

        event.player_response = response
        event.empathy = ai_result["empathy"]
        event.practicality = ai_result["practicality"]
        event.leadership = ai_result["leadership"] #Block which stores the player's response and the individual AI scores in the event record.

        # The application calculates the overall result from the individual
        # category scores instead of accepting a final score from Gemini.
        event.ai_score = calculate_score(
            event.empathy,
            event.practicality,
            event.leadership,
        ) #Helper function that calculates the overall score from the indvidual category scores returned by the AI.

        event.ai_feedback = ai_result["feedback"]
        event.is_resolved = True
        event.resolved_at = timezone.now()
        event.save() #Stores feedback, marks event as resolved and timestamps the resolution in the database.

        # The effect service scales and applies the consequences to the kingdom,
        # then stores the exact effects for later comparison in the report.
        apply_event_response_effects(event) #Applies the scaled effects of the event to the kingdom after adjusting the predefined effects based on the player's AI score.

        # Redirect-after-POST prevents a page refresh from resolving the event
        # again.
        return redirect("event_detail", event_id=event.id) #Player is immediately redirected to the event detail page, the event object is passed into the template so that feedback is instantly accessible.

    return render(
        request,
        "kingdoms/event_response.html",
        {
            # The template uses the event type to choose artwork and displays
            # its human-readable name, turn number, and description.
            "event": event,
        },
    )


class EventHistoryListView(LoginRequiredMixin, ListView):
    """Display the current kingdom's events with pagination."""

    model = Event
    template_name = "kingdoms/event_history.html"

    # The template iterates over ``events`` rather than Django's default
    # ``object_list``.
    context_object_name = "events"

    # Pagination limits each page to twenty records. Django automatically adds
    # ``page_obj``, ``paginator``, and ``is_paginated`` to the context, which
    # the template uses to render previous and next page controls.
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        """Require an existing kingdom before handling the request."""
        # LoginRequiredMixin checks authentication. This additional check
        # confirms that the account also owns the gameplay object required by
        # the queryset.
        if not hasattr(request.user, "kingdom"):
            messages.info(
                request,
                "You need to create a kingdom before accessing event history.",
            )
            return redirect("create_kingdom")

        return super().dispatch(request, *args, **kwargs) #*********

    def get_queryset(self):
        """Return only events belonging to the current kingdom."""
        # Ownership filtering prevents a user from seeing another player's
        # history. Newest event turns appear first.
        return Event.objects.filter(
            kingdom=self.request.user.kingdom,
        ).order_by("-turn_number") 


@login_required
def event_detail(request, event_id):
    """Display one event report and acknowledge its notification.

    Args:
        request: The authenticated Django HTTP request.
        event_id: Primary key of the event being requested.

    Returns:
        ``kingdoms/event_detail.html`` or a redirect to kingdom creation.
    """
    if not hasattr(request.user, "kingdom"):
        messages.info(
            request,
            "You need to create a kingdom before accessing event detail.",
        )
        return redirect("create_kingdom") 

    # Including the current kingdom in the lookup prevents access to another
    # player's event by changing the numeric ID in the URL.
    event = get_object_or_404(
        Event,
        id=event_id,
        kingdom=request.user.kingdom,
    ) #Checks whether the event with the given ID exists and belongs to the user's kingdom. If not, a 404 error is returned.

    
    original_effects = EVENT_EFFECTS.get(event.event_type, {}) #Retrieve the event's original predefined consequences.

    # Build rows comparing the original effects with the scaled values that
    # were actually applied after evaluating the player's response.
    effect_comparison = build_effect_comparison(
        original_effects,
        event.applied_effects,
    ) #Builds a comparison table of the original effects and the scaled effects that were applied after AI evaluation.

    # The previous state is retained for display before the database flag is
    # changed. The template shows whether the player has just opened a new
    # report or revisited an older one.
    was_unseen = not event.report_seen #Checks if the event has been seen by the player, used in template to condition text for new vs previously viewed reports.

    if not event.report_seen:
        event.report_seen = True
        event.save(update_fields=["report_seen"]) #Now that the player has opened the event report, the flag is updated in the database to mark the event as seen.

    kingdom = request.user.kingdom
    kingdom.refresh_war_availability() #War availability is refreshed as the kingdom has been active by viewing an event report.

    return render(
        request,
        "kingdoms/event_detail.html",
        {
            # Displays event artwork, type, turn number, resolution date,
            # original scenario, player decree, individual AI category scores,
            # final score, and written AI feedback.
            "event": event,

            # Controls the newly viewed or previously viewed report message.
            "was_unseen": was_unseen,

            # Iterated as report rows showing the effect label, original value,
            # applied value, and amount mitigated by the response.
            "effect_comparison": effect_comparison,
        },
    )


class TurnHistoryListView(LoginRequiredMixin, ListView):
    """Display the current kingdom's historical turn snapshots."""

    model = TurnHistory
    template_name = "kingdoms/turn_history.html"

    # The template loops over ``turns`` and displays each snapshot's headline
    # statistics and related event.
    context_object_name = "turns"

    # Django automatically adds pagination context values used by the template.
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        """Require an existing kingdom before showing turn history."""
        if not hasattr(request.user, "kingdom"):
            messages.info(
                request,
                "You need to create a kingdom before accessing turn history.",
            )
            return redirect("create_kingdom")

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        """Return the current kingdom's newest turn records first."""
        return TurnHistory.objects.filter(
            kingdom=self.request.user.kingdom,
        ).order_by("-turn_number") #Exact same mechanism as the event history view, but applied to turn history records instead of events.


@login_required
def turn_detail(request, turn_id):
    """Display a historical turn snapshot and mark its report as seen.

    Args:
        request: The authenticated Django HTTP request.
        turn_id: Primary key of the requested TurnHistory record.

    Returns:
        ``kingdoms/turn_detail.html`` or a redirect to kingdom creation.
    """
    if not hasattr(request.user, "kingdom"):
        messages.info(
            request,
            "You need to create a kingdom before accessing turn detail.",
        )
        return redirect("create_kingdom")

    # The kingdom constraint acts as object-level authorisation.
    turn = get_object_or_404(
        TurnHistory,
        id=turn_id,
        kingdom=request.user.kingdom,
    )

    was_unseen = not turn.report_seen

    # Opening the detail page removes the corresponding unread notification
    # from the dashboard.
    if not turn.report_seen:
        turn.report_seen = True
        turn.save(update_fields=["report_seen"])

    kingdom = request.user.kingdom
    kingdom.refresh_war_availability()

    return render(
        request,
        "kingdoms/turn_detail.html",
        {
            # Displays all statistics and policies stored at the completion of
            # the selected turn. Through ``turn.event`` it also displays and
            # links to any crisis associated with that snapshot.
            "turn": turn,

            # Controls the new-report or previously viewed message.
            "was_unseen": was_unseen,
        },
    ) #Exact same mechanism as the event detail view, but applied to turn history records instead of events.


@login_required
def delete_kingdom(request):
    """Delete a kingdom only after exact text confirmation.

    Deleting a kingdom is destructive and may cascade to related turn, event,
    war, battle, and limit records. The view therefore requires the player to
    type ``DELETE KINGDOM`` exactly before deletion occurs.

    Args:
        request: The authenticated Django HTTP request.

    Returns:
        ``kingdoms/delete_kingdom.html`` or a redirect to kingdom creation.
    """
    if not hasattr(request.user, "kingdom"):
        messages.info(
            request,
            "You need to create a kingdom before deleting it.",
        )
        return redirect("create_kingdom")

    # Ownership is derived from the authenticated session instead of accepting
    # a kingdom ID from the browser.
    kingdom = get_object_or_404(
        Kingdom,
        owner=request.user,
    )

    # Preserve the name because the Kingdom instance is unavailable after
    # deletion for user message.
    kingdom_name = kingdom.name
    kingdom_exists = True

    if request.method == "POST":
        confirmation = request.POST.get("confirmation", "").strip()

        if confirmation != "DELETE KINGDOM":
            return render(
                request,
                "kingdoms/delete_kingdom.html",
                {
                    # Intended to identify the kingdom being deleted.
                    "kingdom_name": kingdom_name,

                    # Keeps the confirmation interface visible.
                    "kingdom_exists": True,

                    # Displayed beneath the confirmation control.
                    "error": (
                        "You must type DELETE KINGDOM exactly to confirm."
                    ),
                },
            ) #Same as delete account in core views

        kingdom.delete()
        kingdom_exists = False

    return render(
        request,
        "kingdoms/delete_kingdom.html",
        {
            # Displayed in both the confirmation heading and the successful
            # deletion message.
            "kingdom_name": kingdom_name,

            # Switches the template between its confirmation and completed
            # states.
            "kingdom_exists": kingdom_exists,
        },
    )


@login_required
def kingdom_settings(request):
    """Display and update the current kingdom's settings.

    The settings form is given both the model instance and the kingdom as
    additional context because available customisation options can depend on
    premium status and unlock conditions.

    Args:
        request: The authenticated Django HTTP request.

    Returns:
        ``kingdoms/settings.html`` or a redirect to kingdom creation.
    """
    if not hasattr(request.user, "kingdom"):
        messages.info(
            request,
            "You need to create a kingdom before accessing kingdom settings.",
        )
        return redirect("create_kingdom")

    kingdom = request.user.kingdom

    if request.method == "POST":
        form = KingdomSettingsForm(
            request.POST,
            instance=kingdom,
            kingdom=kingdom,
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Kingdom settings updated successfully.",
            )

            # Redirect-after-POST avoids duplicate updates on refresh.
            return redirect("kingdom_settings")
    else:
        form = KingdomSettingsForm(
            instance=kingdom,
            kingdom=kingdom,
        )

    return render(
        request,
        "kingdoms/settings.html",
        {
            # Rendered through ``form.as_p`` to display editable kingdom
            # settings and any validation messages.
            "form": form,

            # Supplies banner and crest previews, premium checks, unlock state,
            # kingdom name, ruler, turn number, and current account context.
            "kingdom": kingdom,
        },
    )


@login_required
def kingdom_statistics(request):
    """Prepare current, comparative, and historical kingdom statistics.

    The view supplies headline kingdom values, a comparison with an earlier
    turn, historical table rows, and ordered datasets for Chart.js.

    Args:
        request: The authenticated Django HTTP request.

    Returns:
        ``kingdoms/statistics.html`` or a redirect to kingdom creation.
    """
    if not hasattr(request.user, "kingdom"):
        messages.info(
            request,
            "You need to create a kingdom before accessing kingdom statistics.",
        )
        return redirect("create_kingdom")

    kingdom = request.user.kingdom

    # Chronological ordering is required for both the historical table and the
    # chart datasets.
    turns = kingdom.history.order_by("turn_number") #Retrieves all historical turn snapshots in order for charting and comparison.

    # The latest history record generally represents the same completed state
    # as the live Kingdom. The second-latest snapshot therefore provides the
    # preceding state for a meaningful comparison.
    previous_turn = turns[len(turns) - 2] if len(turns) >= 2 else None #If there are at least two historical turns, the second-latest turn is retrieved for comparison with the latest turn. If there is only one or no historical turns, previous_turn is set to None.

    turn_comparison = None #Variable initialized to None to hold the differences between the latest turn and the previous turn. If there is no previous turn, it remains None.

    if previous_turn:
        # These pre-calculated differences allow the template to focus on
        # formatting and presentation rather than arithmetic.
        turn_comparison = {
            "population": kingdom.population - previous_turn.population,
            "treasury": kingdom.treasury - previous_turn.treasury,
            "food": kingdom.food - previous_turn.food,
            "happiness": kingdom.happiness - previous_turn.happiness,
            "stability": kingdom.stability - previous_turn.stability,
            "army_size": kingdom.army_size - previous_turn.army_size,
        } #Differences between the current kingdom statistics and previous turn's statistics are calculated and stored in a dictionary for the template to display.

    # Each list follows the same chronological order. JavaScript can therefore
    # use one index to refer to the same historical turn across all series.
    chart_data = {
        "labels": [turn.turn_number for turn in turns],
        "population": [turn.population for turn in turns],
        "treasury": [turn.treasury for turn in turns],
        "food": [turn.food for turn in turns],
        "happiness": [turn.happiness for turn in turns],
        "stability": [turn.stability for turn in turns],
        "army_size": [turn.army_size for turn in turns],
        "army_quality": [turn.army_quality for turn in turns],
        "a_eff": [turn.a_eff for turn in turns],
        "infra": [turn.infra for turn in turns],
    } #Chart data prepared as a dictionary of lists, where each list contains the values of a specific statistic across all historical turns. The labels list contains the turn numbers for the x-axis of the chart.

    kingdom.refresh_war_availability()

    return render(
        request,
        "kingdoms/statistics.html",
        {
            # Displays the kingdom name, premium status, current turn, headline
            # statistics, and controls whether the CSV link and premium chart
            # interface are available.
            "kingdom": kingdom,

            # Iterated in the premium historical table. The template displays
            # each turn's population, treasury, food, happiness, stability,
            # army size, and infrastructure.
            "history": turns,

            # Embedded safely through Django's ``json_script`` filter. The
            # statistics JavaScript reads it and constructs the Chart.js
            # visualisations.
            "chart_data": chart_data,

            # Displays the change in each major metric since the previous
            # comparable snapshot. It is shown only for premium users with
            # sufficient history.
            "turn_comparison": turn_comparison,
        },
    )


@login_required
def export_turn_history_csv(request):
    """Export turn history as a premium CSV download.

    This view does not render a template. It creates a CSV response in memory,
    with one historical turn per row.

    Args:
        request: The authenticated Django HTTP request.

    Returns:
        A downloadable CSV response, or a redirect when the user has no kingdom
        or does not have premium access.
    """
    if not hasattr(request.user, "kingdom"):
        messages.info(
            request,
            "You need to create a kingdom before exporting turn history.",
        )
        return redirect("create_kingdom")

    kingdom = request.user.kingdom

    # The template hides the export link from standard users, but access must
    # still be enforced here because a URL can be requested directly.
    if not kingdom.is_premium:
        messages.warning(
            request,
            "CSV exports are a Premium feature.",
        )
        return redirect("payments:pricing")

    response = HttpResponse(content_type="text/csv")

    # This header instructs the browser to download the response and supplies a
    # filename based on the kingdom slug.
    response["Content-Disposition"] = (
        f'attachment; filename="{kingdom.slug}-turn-history.csv"'
    )

    writer = csv.writer(response)

    # The first row contains human-readable column labels for spreadsheet use.
    writer.writerow([
        "Turn",
        "Population",
        "Treasury",
        "Food",
        "Happiness",
        "Stability",
        "Army Size",
        "Army Quality",
        "Agricultural Efficiency",
        "Infrastructure",
        "Tax Rate",
        "Agriculture Investment",
        "Infrastructure Investment",
        "Military Investment",
        "Welfare Investment",
        "Event",
        "Created At",
    ])

    # Records are exported in chronological order to support direct comparison,
    # charting, and analysis in spreadsheet software.
    for turn in kingdom.history.order_by("turn_number"):
        writer.writerow([
            turn.turn_number,
            turn.population,
            round(turn.treasury, 2),
            round(turn.food, 2),
            round(turn.happiness, 2),
            round(turn.stability, 2),
            turn.army_size,
            round(turn.army_quality, 2),
            round(turn.a_eff, 3),
            round(turn.infra, 3),
            round(turn.tax_rate, 2),
            round(turn.agriculture_investment, 2),
            round(turn.infrastructure_investment, 2),
            round(turn.military_investment, 2),
            round(turn.welfare_investment, 2),
            turn.event_type or "",
            turn.created_at.isoformat(),
        ])

    return response