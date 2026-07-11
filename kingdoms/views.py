import csv

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.http import require_POST
from django.views.generic import ListView
from django.utils import timezone
from django.utils.text import slugify
from django.http import HttpResponse
from django.db import transaction
from .forms import PolicyForm, CreateKingdomForm, KingdomSettingsForm
from .models import Kingdom, TurnHistory, Event, TurnLimit
from wars.models import War
from .simulation import process_turn
from .events import apply_event_response_effects
from core.ai import evaluate_event_response, evaluate_policy_decision
from .events import EVENT_EFFECTS
from .utils import build_effect_comparison, calculate_score, next_midnight

# Create your views here.

@login_required
def dashboard(request):

    if not hasattr(request.user, "kingdom"):
        messages.info(
            request,
            "You need to create a kingdom before accessing the dashboard.",
        )
        return redirect("create_kingdom")

    kingdom = request.user.kingdom

    kingdom.refresh_war_availability()

    unresolved_event = kingdom.events.filter(
        is_resolved=False,
    ).first()

    unseen_turns = kingdom.history.filter(
        report_seen=False,
    ).all()

    pending_war_received = kingdom.wars_received.filter(
        status="pending_defender",
    ).first()

    pending_war_started = kingdom.wars_started.filter(
        status="pending_defender",
    ).first()

    unseen_battle_reports_started = kingdom.wars_started.filter(
        status="resolved",
        battle__report_seen=False,
    ).order_by("-resolved_at")

    unseen_battle_reports_received = kingdom.wars_received.filter(
        status="resolved",
        battle__report_seen=False,
    ).order_by("-resolved_at")

    turn_limit = kingdom.turn_limit
    turn_limit.refresh_daily_turns()

    if not turn_limit.cooldown_active():
        turn_limit.cooldown_ends_at = None
        turn_limit.save(update_fields=["cooldown_ends_at"])

    turn_blocked = False
    turn_blocked_reason = ""

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
            )

    if request.method == "POST":
        form = PolicyForm(
            request.POST,
            instance=kingdom,
        )

        if form.is_valid():
            form.save()

            if kingdom.is_premium:
                policy_advice = evaluate_policy_decision(
                    kingdom,
                    form.cleaned_data,
                )

                kingdom.policy_advice = policy_advice

                kingdom.save(
                    update_fields=[
                        "policy_advice"
                    ]
                )

                success_message = (
                    "Policies saved. Your premium royal council "
                    "has prepared advice."
                )

            else:
                success_message = (
                    "Policies saved. Upgrade to Premium to unlock "
                    "royal council advice."
                )

            messages.success(
                request,
                success_message,
            )

            return redirect("dashboard")

    else:
        form = PolicyForm(instance=kingdom)

    return render(
        request,
        "kingdoms/dashboard.html",
        {
            "kingdom": kingdom,
            "form": form,
            "turn_limit": turn_limit,
            "turn_blocked": turn_blocked,
            "turn_blocked_reason": turn_blocked_reason,
            "unseen_turns": unseen_turns,
            "unresolved_event": unresolved_event,
            "pending_war_received": pending_war_received,
            "pending_war_started": pending_war_started,
            "unseen_battle_reports_received": (
                unseen_battle_reports_received
            ),
            "unseen_battle_reports_started": (
                unseen_battle_reports_started
            )
        },
    )

@login_required
def create_kingdom(request):
    if hasattr(request.user, "kingdom"):
        return redirect("dashboard")

    if request.method == "POST":
        form = CreateKingdomForm(request.POST)
        if form.is_valid():
            kingdom = form.save(commit=False)
            kingdom.owner = request.user
            kingdom.ruler_name = request.user.username
            kingdom.slug = slugify(kingdom.name)
            kingdom.save()
            daily_limit = 6 if kingdom.is_premium else 3

            TurnLimit.objects.create(
                kingdom=kingdom,
                daily_turn_limit=daily_limit,
                turns_remaining_today=daily_limit,
                daily_reset_at=next_midnight(),
            )
            return redirect("dashboard")
    else:
        form = CreateKingdomForm()

    return render(request, "kingdoms/create_kingdom.html", {"form": form})

@login_required
@require_POST
def take_turn(request):
    kingdom = getattr(request.user, "kingdom", None)

    if kingdom is None:
        return redirect("create_kingdom")
    
    kingdom.refresh_war_availability()
    
    if kingdom.events.filter(is_resolved=False).exists():
        messages.warning(
            request,
            "You must resolve the current crisis before advancing the realm."
        )
        return redirect("dashboard")

    turn_limit = kingdom.turn_limit
    turn_limit.refresh_daily_turns()
    if not turn_limit.can_take_turn():
        if turn_limit.cooldown_active():
            messages.warning(
                request,
                'You cannot take a turn at this moment, please wait until the cooldown period has expired'
            )
        else:
            messages.warning(
                request,
                'You have no turns remaining, please try again tomorrow'
            )    
        return redirect('dashboard')    
    
    kingdom.policy_advice = None

    with transaction.atomic():
        event, turn = process_turn(kingdom)
        turn_limit.use_turn()

        if event:
            data = EVENT_EFFECTS.get(event, {})

            Event.objects.create(
                kingdom=kingdom,
                turn=turn,
                turn_number=turn.turn_number,
                event_type=event,
                description=data.get("description", "")
            )

    return render(
        request,
        "kingdoms/turn_feedback.html",
        {
            "turn": turn
        },
    )

@login_required
def respond_to_event(request, event_id):
    event = get_object_or_404(
        Event,
        id=event_id,
        kingdom=request.user.kingdom, 
        is_resolved=False
    )

    kingdom = request.user.kingdom
    kingdom.refresh_war_availability()
    

    if request.method == "POST":
        response = request.POST.get("response", "").strip()

        if not response:
            return render(
                request,
                "kingdoms/event_response.html",
                {
                    "event": event,
                    "error": "You must write a royal decree.",
                }
            )

        ai_result = evaluate_event_response(
            event=event,
            player_response=response,
        )

        event.player_response = response
        event.empathy = ai_result["empathy"]
        event.practicality = ai_result["practicality"]
        event.leadership = ai_result["leadership"]
        event.ai_score = calculate_score(event.empathy, event.practicality, event.leadership)
        event.ai_feedback = ai_result["feedback"]
        event.is_resolved = True
        event.resolved_at = timezone.now()
        event.is_resolved = True
        event.save()
        apply_event_response_effects(event)
        return redirect("event_detail", event_id=event.id)
    
    return render(
        request,
        "kingdoms/event_response.html",
        {"event": event}
    )

class EventHistoryListView(LoginRequiredMixin, ListView):
    model = Event
    template_name = "kingdoms/event_history.html"
    context_object_name = "events"
    paginate_by = 20

    def get_queryset(self):
        return Event.objects.filter(
            kingdom=self.request.user.kingdom
        ).order_by("-turn_number")

@login_required
def event_detail(request, event_id):
    event = get_object_or_404(
        Event,
        id=event_id,
        kingdom=request.user.kingdom, 
    )

    original_effects = EVENT_EFFECTS.get(event.event_type, {})

    effect_comparison = build_effect_comparison(
        original_effects,
        event.applied_effects
    )  

    was_unseen = not event.report_seen

    if not event.report_seen:
        event.report_seen = True
        event.save(update_fields=["report_seen"])

    kingdom = request.user.kingdom
    kingdom.refresh_war_availability()

    return render(
        request,
        "kingdoms/event_detail.html",
        {
            "event": event,
            "was_unseen": was_unseen,
            "effect_comparison": effect_comparison
         }
    )
    
class TurnHistoryListView(LoginRequiredMixin, ListView):
    model = TurnHistory
    template_name = "kingdoms/turn_history.html"
    context_object_name = "turns"
    paginate_by = 20

    def get_queryset(self):
        return TurnHistory.objects.filter(
            kingdom=self.request.user.kingdom
        ).order_by("-turn_number")


@login_required
def turn_detail(request, turn_id):
    turn = get_object_or_404(
        TurnHistory,
        id=turn_id,
        kingdom=request.user.kingdom, 
    )

    was_unseen = not turn.report_seen
    turn.report_seen = True
    turn.save(update_fields=["report_seen"])

    kingdom = request.user.kingdom
    kingdom.refresh_war_availability()

    return render(
        request,
        "kingdoms/turn_detail.html",
        {
            "turn": turn,
            "was_unseen": was_unseen
         }
    )

@login_required
def delete_kingdom(request):
    kingdom = get_object_or_404(
        Kingdom,
        owner=request.user,
    )

    kingdom_name = kingdom.name

    kingdom_exists = True

    if request.method == "POST":
        confirmation = request.POST.get("confirmation", "").strip()

        if confirmation != "DELETE KINGDOM":
            return render(
                request,
                "kingdoms/delete_kingdom.html",
                {
                    "kingdom": kingdom,
                    "error": "You must type DELETE KINGDOM exactly to confirm.",
                }
            )

        kingdom.delete()
        kingdom_exists = False

    return render(
        request,
        "kingdoms/delete_kingdom.html",
        {
            "kingdom": kingdom_name,
            "kingdom_exists": kingdom_exists 
        }
    )

@login_required
def kingdom_settings(request):

    if not hasattr(request.user, "kingdom"):
        
        messages.info(
            request,
            "You need to create a kingdom before accessing kingdom settings."
        )

        return redirect("create_kingdom")
    
    kingdom = request.user.kingdom

    if request.method == "POST":
        form = KingdomSettingsForm(
            request.POST,
            instance=kingdom,
            kingdom=kingdom
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Kingdom settings updated successfully."
            )

            return redirect("kingdom_settings")

    else:
        form = KingdomSettingsForm(
            instance=kingdom,
            kingdom=kingdom
        )

    return render(
        request,
        "kingdoms/settings.html",
        {
            "form": form,
            "kingdom": kingdom,
        }
    )

@login_required
def kingdom_statistics(request):
    if not hasattr(request.user, "kingdom"):
        messages.info(
            request,
            "You need to create a kingdom before accessing kingdom statistics."
        )
        return redirect("create_kingdom")
    kingdom = request.user.kingdom
    turns = kingdom.history.order_by("turn_number")
    previous_turn = turns[len(turns) - 2] if len(turns) >= 2 else None

    turn_comparison = None
    if previous_turn:
        turn_comparison = {
            "population": kingdom.population - previous_turn.population,
            "treasury": kingdom.treasury - previous_turn.treasury,
            "food": kingdom.food - previous_turn.food,
            "happiness": kingdom.happiness - previous_turn.happiness,
            "stability": kingdom.stability - previous_turn.stability,
            "army_size": kingdom.army_size - previous_turn.army_size,
        }

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
    }
    kingdom.refresh_war_availability()

    return render(
        request,
        "kingdoms/statistics.html",
        {
            "kingdom": kingdom,
            "history": turns,
            "chart_data": chart_data,
            "turn_comparison": turn_comparison,
        }
    )


@login_required
def export_turn_history_csv(request):
    if not hasattr(request.user, "kingdom"):
        messages.info(
            request,
            "You need to create a kingdom before exporting turn history."
        )
        return redirect("create_kingdom")

    kingdom = request.user.kingdom
    if not kingdom.is_premium:
        messages.warning(
            request,
            "CSV exports are a Premium feature."
        )
        return redirect("payments:pricing")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="{kingdom.slug}-turn-history.csv"'
    )

    writer = csv.writer(response)
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
