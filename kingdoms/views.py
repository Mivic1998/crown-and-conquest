from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.http import require_POST
from django.views.generic import ListView
from django.utils import timezone
from django.utils.text import slugify
from .forms import PolicyForm, CreateKingdomForm, KingdomSettingsForm
from .models import Kingdom, TurnHistory, Event, TurnLimit
from .simulation import process_turn
from. events import apply_event_response_effects
from .ai import evaluate_event_response
from .events import EVENT_EFFECTS
from .utils import build_effect_comparison, calculate_score
from .utils import next_midnight

# Create your views here.

@login_required
def dashboard(request):

    if not hasattr(request.user, "kingdom"):
        return redirect("create_kingdom")

    kingdom = request.user.kingdom

    unresolved_event = kingdom.events.filter(
        is_resolved=False
    ).first()

    turn_limit = kingdom.turn_limit
    turn_limit.refresh_daily_turns()
    if not turn_limit.cooldown_active():
        turn_limit.cooldown_ends_at = None
 
    turn_blocked = False
    turn_blocked_reason = ""

    if unresolved_event:
        turn_blocked = True
        turn_blocked_reason = "You must respond to the current crisis before advancing."

    elif not turn_limit.can_take_turn():
        turn_blocked = True

        if turn_limit.cooldown_active():
            turn_blocked_reason = "You must wait for the turn cooldown to expire."
        else:
            turn_blocked_reason = "You have no turns remaining today."

    if request.method == "POST":
        form = PolicyForm(request.POST, instance=kingdom)
        if form.is_valid():
            form.save()
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
            "unresolved_event": unresolved_event,
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
            TurnLimit.objects.create(
                kingdom=kingdom,
                daily_reset_at=next_midnight()
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

    turn, event = process_turn(kingdom)

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
            instance=kingdom
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
            instance=kingdom
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
    turns = kingdom.turn_history.order_by("turn_number")
    chart_data = {
        "labels": [turn.turn_number for turn in turns],
        "population": [turn.population for turn in turns],
        "treasury": [turn.treasury for turn in turns],
        "food": [turn.food for turn in turns],
        "happiness": [turn.happiness for turn in turns],
        "stability": [turn.stability for turn in turns],
    }

    return render(
        request,
        "kingdoms/statistics.html",
        {
            "kingdom": kingdom,
            "turn_history": turns,
            "chart_data": chart_data,
        }
    )
