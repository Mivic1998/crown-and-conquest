from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils.text import slugify
from .forms import PolicyForm, CreateKingdomForm
from .models import Kingdom, TurnHistory, Event
from .simulation import process_turn
from .events import EVENT_DATA

# Create your views here.

@login_required
def dashboard(request):

    if not hasattr(request.user, "kingdom"):
        return redirect("create_kingdom")

    kingdom = request.user.kingdom

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

    turn = process_turn(kingdom)

    if turn.event:
        data = EVENT_DATA.get(turn.event, {})

        Event.objects.create(
            kingdom=kingdom,
            turn=turn,
            turn_number=turn.turn_number,
            event_type=turn.event,
            description=data.get("description", ""),

            population_change=data.get("population_change", 0),
            treasury_change=data.get("treasury", 0),
            food_change=data.get("food", 0),
            army_size_change=data.get("army_size", 0),
            army_quality_change=data.get("army_quality", 0),
            happiness_change=data.get("happiness", 0),
            stability_change=data.get("stability", 0),

            duration_turns=data.get("turns", 0),
            food_production_modifier=data.get("production_modifier", 1.0),
            tax_income_modifier=data.get("tax_income_modifier", 1.0),
        )

    return render(
        request,
        "kingdoms/feedback.html",
        {
            "turn": turn
        },
    )

def event_detail(request):
    