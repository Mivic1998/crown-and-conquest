"""Views for diplomacy, war declarations, responses, and battle reports.

This module coordinates the player-facing workflows within the ``wars``
application. It connects authenticated requests to kingdom records, warfare
forms, Gemini rallying-cry evaluation, battle simulation, cooldown rules, and
the templates used to display diplomacy and conflict.

The detailed combat calculations remain in ``wars.simulation``. These views
instead handle:

- authentication and kingdom ownership;
- opponent eligibility;
- strength and cooldown validation;
- rallying-cry submission and AI evaluation;
- creation and progression of War records;
- battle-resolution requests;
- access control for reports;
- preparation of data for warfare templates.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from kingdoms.models import Kingdom
from .models import WarCooldown, War
from .forms import WarForm
from core.ai import evaluate_rallying_cry
from .utils import momentum_hint_for_kingdom
from .simulation import resolve_war_simulation


class DiplomacyView(LoginRequiredMixin, ListView):
    """Display kingdoms that are currently eligible war targets.

    ``LoginRequiredMixin`` blocks unauthenticated access, while ``dispatch``
    applies additional gameplay checks before the queryset is evaluated.

    Eligible opponents must:

    - not be the current player's kingdom;
    - have an active war-availability window;
    - fall within the permitted comparative-strength range;
    - not be protected by an active cooldown involving the attacker.

    The resulting kingdoms are passed to ``wars/diplomacy.html``.
    """

    model = Kingdom
    template_name = "wars/diplomacy.html"

    # The template iterates over ``kingdoms`` rather than Django's default
    # ``object_list`` context name.
    context_object_name = "kingdoms"

    def dispatch(self, request, *args, **kwargs):
        """Check kingdom ownership and pending-war state before dispatch.

        Args:
            request: The authenticated Django HTTP request.
            *args: Positional arguments supplied by Django.
            **kwargs: URL keyword arguments supplied by Django.

        Returns:
            A redirect when diplomacy is unavailable, otherwise the standard
            ``ListView`` response.
        """
        # Authentication does not guarantee that the user has completed kingdom
        # creation. Accessing ``request.user.kingdom`` without this check would
        # raise a reverse one-to-one relationship exception.
        if not hasattr(request.user, "kingdom"):
            messages.info(
                request,
                "You need to create a kingdom before accessing diplomacy.",
            )
            return redirect("create_kingdom")

        kingdom = request.user.kingdom

        # Diplomacy is unavailable while either an initiated or received war
        # remains in the defender-response stage. This prevents overlapping wars
        # from being initiated through the normal interface.
        has_pending_war = (
            kingdom.wars_started.filter(
                status="pending_defender",
            ).exists()
            or kingdom.wars_received.filter(
                status="pending_defender",
            ).exists()
        ) #Checks whether the current kingdom has any unresolved wars, making diplomacy unavailable until the war is resolved.

        if has_pending_war:
            messages.info(
                request,
                "You must resolve the current war before accessing diplomacy.",
            )
            return redirect("dashboard")

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        """Return all eligible kingdoms that the current player may challenge.

        Returns:
            A list of ``Kingdom`` instances filtered by availability, military
            strength, and active bilateral cooldowns.
        """
        my_kingdom = self.request.user.kingdom
        now = timezone.now()

        # Remove the player's own kingdom and require an availability timestamp
        # that has not yet expired.
        queryset = Kingdom.objects.exclude(
            id=my_kingdom.id,
        ).filter(
            war_available_until__gte=now,
        )

        # Baseline strength combines army quantity and army quality so that a
        # large but poorly trained army is not treated as identical to an
        # equally large, highly trained force.
        my_strength = (
            my_kingdom.army_size
            * my_kingdom.army_quality
        )

        # Opponents must remain within a broad comparative-strength range. The
        # same rule is repeated inside ``declare_war`` because queryset filtering
        # only controls what is displayed and cannot secure the endpoint.
        min_strength = my_strength * 0.65
        max_strength = my_strength * 1.45

        queryset = [
            kingdom
            for kingdom in queryset
            if min_strength
            <= kingdom.army_size * kingdom.army_quality
            <= max_strength
        ]

        # Retrieve only the defender IDs affected by an active cooldown for this
        # attacking kingdom. A set provides efficient repeated membership checks.
        blocked_defender_ids = set(
            WarCooldown.objects.filter(
                attacker=my_kingdom,
                cooldown_ends_at__gt=now,
            ).values_list(
                "defender_id",
                flat=True,
            )
        ) #Blocks kingdoms that are currently under a cooldown period from being attacked by the user's kingdom.

        queryset = [
            kingdom
            for kingdom in queryset
            if kingdom.id not in blocked_defender_ids
        ] #Applies filters so only eligible kingdoms remain in the queryset.

        return queryset


@login_required
def declare_war(request, slug):
    """Display and process a declaration of war against one kingdom.

    The view repeats every important eligibility rule before accepting the
    declaration. This protects the workflow from direct URL or POST requests
    that bypass the diplomacy page.

    A valid POST sends the attacker's rallying cry to Gemini, stores the
    structured evaluation on a new ``War`` record, and marks both kingdoms as
    being at war.

    Args:
        request: The authenticated Django HTTP request.
        slug: The unique slug identifying the intended defender.

    Returns:
        ``wars/declare_war.html`` for an eligible target, or a redirect when a
        declaration rule is not satisfied.
    """
    kingdom = getattr(request.user, "kingdom", None)

    if kingdom is None:
        messages.error(request, "You must have a kingdom to declare war.")
        return redirect("create_kingdom")

    # The target originates from the URL, so ``get_object_or_404`` safely handles
    # invalid or missing slugs.
    enemy_kingdom = get_object_or_404(Kingdom, slug=slug) #Ensures that the defender kingdom exists, otherwise throws an error. Exists to protect against direct URL manipulation and bypassing the diplomacy page.
    now = timezone.now()

    # Prevent self-declaration even if the user manually constructs the URL.
    if enemy_kingdom == kingdom:
        messages.error(request, "You cannot declare war on your own kingdom.")
        return redirect("wars:diplomacy") #Displays the relevant error message and redirects user back to the diplomacy page.

    # A kingdom may only be challenged while its temporary war-availability
    # window remains active.
    if (
        enemy_kingdom.war_available_until is None
        or enemy_kingdom.war_available_until < now
    ):
        messages.error(request, "This kingdom is currently unavailable for war.")
        return redirect("wars:diplomacy") #Prevents initiating conflict with inactive kingdoms via direct URL manipulation.

    # The attacker cannot begin another conflict while already participating in
    # an unresolved war.
    if kingdom.is_at_war is True:
        messages.error(request, "You cannot declare a war while you are still at war.")
        return redirect("wars:war_pending")

    # A defender already engaged elsewhere cannot be selected as a new target.
    if enemy_kingdom.is_at_war is True:
        messages.error(request, "This kingdom is currently at war and cannot be attacked.")
        return redirect("wars:diplomacy")

    attacker_strength = kingdom.army_size * kingdom.army_quality
    defender_strength = enemy_kingdom.army_size * enemy_kingdom.army_quality

    min_strength = attacker_strength * 0.65
    max_strength = attacker_strength * 1.45

    # These checks repeat the DiplomacyView filters because frontend filtering
    # alone would not stop a direct request against an ineligible target.
    if defender_strength < min_strength:
        messages.error(request, "This kingdom is too weak for war.")
        return redirect("wars:diplomacy")

    if defender_strength > max_strength:
        messages.error(request, "This kingdom is too strong for war.")
        return redirect("wars:diplomacy")

    # The cooldown applies to this specific attacker-defender relationship,
    # allowing other valid diplomatic interactions to remain possible.
    if WarCooldown.objects.filter(
        attacker=kingdom,
        defender=enemy_kingdom,
        cooldown_ends_at__gt=now,
    ).exists():
        messages.error(
            request,
            "You cannot declare war on this kingdom due to a cooldown.",
        )
        return redirect("wars:diplomacy")

    # A second protection prevents any kingdom from being attacked repeatedly
    # within two hours, even by different attackers.
    if enemy_kingdom.last_attacked_at and (now - enemy_kingdom.last_attacked_at).total_seconds() < 7200:
        messages.error(
            request,
            "You cannot declare war on this kingdom because it was attacked within the last two hours.",
        )
        return redirect("wars:diplomacy")

    if request.method == "POST":
        form = WarForm(request.POST)

        if form.is_valid():
            # WarForm has already stripped whitespace and enforced the rallying
            # cry's permitted length.
            rallying_cry = form.cleaned_data["rallying_cry"].strip()

            # Gemini evaluates leadership, inspiration, and practicality. The AI
            # helper also returns a bounded modifier and safe fallback values if
            # the external service is unavailable.
            ai_result = evaluate_rallying_cry(rallying_cry)

            # Store the rallying cry and AI assessment with the declaration.
            # Battle resolution can later consume these persisted values without
            # making another request for the attacker.
            war = War.objects.create(
                attacker=kingdom,
                defender=enemy_kingdom,
                status="pending_defender",
                attacker_rallying_cry=rallying_cry,
                defender_response_deadline=now + timedelta(hours=3),
                attacker_leadership_score=ai_result["leadership_score"],
                attacker_inspiration_score=ai_result["inspiration_score"],
                attacker_practicality_score=ai_result["practicality_score"],
                attacker_rally_modifier=ai_result["rally_modifier"],
                attacker_ai_feedback=ai_result["feedback"],
            )

            # Mark both live kingdom records as engaged so neither may begin or
            # receive another conflict before this one is resolved.
            enemy_kingdom.is_at_war = True
            enemy_kingdom.save(update_fields=["is_at_war"])
            kingdom.is_at_war = True
            kingdom.save(update_fields=["is_at_war"])

            return redirect("wars:war_pending")

    else:
        form = WarForm()

    # The utility converts hidden numeric momentum into a qualitative scouting
    # description rather than exposing the exact battle modifier.
    momentum_hint = momentum_hint_for_kingdom(enemy_kingdom)

    return render(
        request,
        "wars/declare_war.html",
        {
            # Rendered with ``form.as_p`` as the rallying-cry submission form.
            "form": form,

            # Displayed in the reconnaissance section as a description of the
            # defender's recent military momentum.
            "momentum_hint": momentum_hint,

            # Supplies the defender's name, ruler, army size, army quality, and
            # win/loss record shown before the declaration is confirmed.
            "enemy_kingdom": enemy_kingdom,
        },
    )


@login_required
def war_pending(request):
    """Display a war initiated by the current kingdom while awaiting response.

    If the defender deadline has expired, the view invokes automatic battle
    resolution and redirects the attacker to the completed battle report.

    Args:
        request: The authenticated Django HTTP request.

    Returns:
        ``wars/war_pending.html``, the battle-report redirect, or kingdom
        creation if no kingdom exists.
    """
    if not hasattr(request.user, "kingdom"):
        messages.error(request, "You must have a kingdom to have declared a war.")
        return redirect("create_kingdom")

    kingdom = request.user.kingdom

    # Restrict the lookup to an unresolved war initiated by the current kingdom.
    war = get_object_or_404(
        War,
        attacker=kingdom,
        status="pending_defender"
    )

    # This branch is defensive, although the lookup above normally prevents a
    # resolved War from being returned.
    if war.status == "resolved":
        return redirect(
            "wars:battle_report",
             id=war.id,
        )

    # ``has_expired`` is calculated by the War model from the stored deadline,
    # current time, and current status.
    if war.has_expired:
        # The simulation supplies the defender's timeout behaviour and completes
        # every associated database update.
        resolve_war_simulation(
            war=war
        )

        return redirect(
            "wars:battle_report",
            id=war.id,
        )

    context = {
        # Displays the attacker's rallying cry and response deadline. The
        # deadline is also inserted into a ``data-deadline`` attribute read by
        # ``static/js/war_countdown.js``.
        "war": war,

        # Displays the attacker's name, ruler, army statistics, and war record.
        "kingdom": kingdom,

        # Displays the defender's name, ruler, army statistics, and war record.
        "enemy_kingdom": war.defender,
    }

    return render(
        request,
        "wars/war_pending.html",
        context,
    )


@login_required
def notify_defender(request):
    """Display and process a war declaration received by the current kingdom.

    The defender may submit a rallying cry, which is evaluated through Gemini
    and stored on the existing War record. Actual battle resolution remains a
    separate POST-only workflow.

    Args:
        request: The authenticated Django HTTP request.

    Returns:
        ``wars/war_notification.html`` or a redirect to kingdom creation.
    """
    if not hasattr(request.user, "kingdom"):
        messages.error(request, "You must have a kingdom to receive war notifications.")
        return redirect("create_kingdom")

    # Only the kingdom recorded as defender may view and answer this pending war.
    war = get_object_or_404(War, defender=request.user.kingdom, status="pending_defender")
    kingdom = request.user.kingdom
    enemy_kingdom = war.attacker

    if war.has_expired:
            # The simulation supplies the defender's timeout behaviour and completes
            # every associated database update.
            resolve_war_simulation(
                war=war
            )

            return redirect(
                    "wars:battle_report",
                    id=war.id,
            ) #If the defender has not met the deadline, the war automatically resolves and the user is referred to the relevant battle report

    if request.method == "POST":
        form = WarForm(request.POST)

        if form.is_valid():
            rallying_cry = form.cleaned_data["rallying_cry"].strip()
            war.defender_rallying_cry = rallying_cry

            # Evaluate the defender using the same structured criteria and
            # fallback behaviour used for the attacker.
            ai_result = evaluate_rallying_cry(rallying_cry)

            war.defender_leadership_score = ai_result["leadership_score"]
            war.defender_inspiration_score = ai_result["inspiration_score"]
            war.defender_practicality_score = ai_result["practicality_score"]
            war.defender_rally_modifier = ai_result["rally_modifier"]
            war.defender_ai_feedback = ai_result["feedback"]

            # Restrict the SQL update to the fields modified by this workflow.
            war.save(update_fields=[
                "defender_rallying_cry",
                "defender_leadership_score",
                "defender_inspiration_score",
                "defender_practicality_score",
                "defender_rally_modifier",
                "defender_ai_feedback"
            ])

            # Redirect-after-POST prevents the browser from resubmitting the
            # rallying cry to Gemini when the page is refreshed.
            return redirect("wars:notify_defender")

    else:
        # Preserve a previously submitted rallying cry when the defender returns
        # to the page before resolving the conflict.
        form = WarForm(initial={
            "rallying_cry": war.defender_rallying_cry,
        })

    return render(request, "wars/war_notification.html", {
        # Rendered through ``form.as_p`` as the defender's rallying-cry input.
        "form": form,

        # Displays the attacker's rallying cry and supplies the response deadline
        # consumed by the JavaScript countdown timer.
        "war": war,

        # Represents the defending kingdom. It is supplied in context but is not
        # directly referenced by the current template.
        "kingdom": kingdom,

        # Displays the attacking kingdom's name, army size, army quality, and
        # win/loss record.
        "enemy_kingdom": enemy_kingdom
    })


@login_required
@require_POST
def resolve_war(request):
    """Resolve the current defender's pending war.

    The endpoint accepts POST only because battle resolution modifies several
    persistent records, including both kingdoms, the War, the Battle, and the
    resulting cooldown.

    Args:
        request: The authenticated POST request.

    Returns:
        A redirect to the generated battle report or kingdom creation.
    """
    if not hasattr(request.user, "kingdom"):
        messages.error(request, "You must have a kingdom to resolve a war.")
        return redirect("create_kingdom")

    kingdom = request.user.kingdom

    # Object-level ownership is enforced by requiring the current kingdom to be
    # the defender on the unresolved War.
    war = get_object_or_404(War, defender=kingdom, status="pending_defender")

    # The service performs authoritative combat calculations, updates both live
    # kingdoms, creates the Battle record, resolves the War, and adds cooldowns.
    resolve_war_simulation(war) #Once the defending kingdom has submitted his or her battle cry, the war outcomes are applied using the simulation

    return redirect(
        "wars:battle_report",
        id=war.id #Defender is immediately referred to the relevant battle report
    )


@login_required
def war_list(request):
    """Display all wars initiated and received by the current kingdom.

    Args:
        request: The authenticated Django HTTP request.

    Returns:
        ``wars/my_wars.html`` or a redirect to kingdom creation.
    """
    if not hasattr(request.user, "kingdom"):
        messages.error(request, "You must have a kingdom to view wars.")
        return redirect("create_kingdom")

    kingdom = request.user.kingdom
    is_at_war = kingdom.is_at_war

    # The template renders initiated and received wars in separate sections, so
    # the records are queried independently and ordered newest first.
    wars_initiated = War.objects.filter(attacker=kingdom).order_by("-declared_at")
    wars_received = War.objects.filter(defender=kingdom).order_by("-declared_at")

    return render(request, "wars/my_wars.html", {
        # Iterated in the declared-wars section to display defender, date,
        # status, winner, and pending/report actions.
        "wars_initiated": wars_initiated,

        # Iterated in the received-wars section to display attacker, date,
        # status, winner, and defender/report actions.
        "wars_received": wars_received,

        # Supplies current-kingdom context for role-sensitive presentation.
        "kingdom": kingdom,

        # Controls the active-war warning and determines whether the page links
        # to the attacker pending page or defender notification page.
        "is_at_war": is_at_war
    })


@login_required
def battle_report(request, id):
    """Display a resolved battle report to a participating kingdom.

    Args:
        request: The authenticated Django HTTP request.
        id: Primary key of the War whose related Battle should be displayed.

    Returns:
        ``wars/battle_report.html`` or a redirect to kingdom creation.

    Raises:
        Http404: If the authenticated kingdom was neither attacker nor defender.
    """
    if not hasattr(request.user, "kingdom"):
        messages.error(request, "You must have a kingdom to view battle reports.")
        return redirect("create_kingdom")

    kingdom = request.user.kingdom
    war = get_object_or_404(War, id=id) #Checks whether a war with the given ID exists

    # Authentication alone is insufficient. The current kingdom must have
    # participated in the requested war.
    if war.attacker != kingdom and war.defender != kingdom:
        raise Http404() #User's kingdom must be/have been a participant in the war in order to view report

    # War and Battle use a one-to-one relationship, so the resolved result is
    # available through the reverse ``battle`` attribute.
    battle = war.battle

    # Preserve the previous notification state before marking the report seen.
    was_unseen = True
    if battle.report_seen:
        was_unseen = False #Boolean to check whether the battle report has already been viewed which conditions template accordingly

    # Opening the report acknowledges the unread battle notification displayed
    # elsewhere in the application.
    battle.report_seen = True
    battle.save(update_fields=["report_seen"]) #Report marked as seen

    return render(request, "wars/battle_report.html", {
        # Displays the battle outcome, generated narrative, attacker losses, and
        # defender losses.
        "battle": battle,

        # Supplies the attacker and defender, current armies, both rallying cries,
        # individual AI scores, AI feedback, and timeout state.
        "war": war,

        # Changes the document title between “New Battle Report” and the normal
        # “Battle Report”.
        "was_unseen": was_unseen
    })