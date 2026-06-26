from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils.text import slugify
from .forms import PolicyForm, CreateKingdomForm
from .models import Kingdom, TurnHistory
from .simulation import process_turn
from .events import evaluate_events

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
    process_turn(user_kingdom)
    turn = TurnHistory.objects.filter(kingdom=user_kingdom).latest()
    event = evaluate_events(kingdom)
    if(event):
        turn.event = event
        turn.save()
    return render(
        request,
        "kingdoms/feedback.html",
        {
            "turn": turn
        },
    )    
    
    



    