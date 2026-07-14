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

# Create your views here.

class DiplomacyView(LoginRequiredMixin, ListView):
    model = Kingdom
    template_name = "wars/diplomacy.html"
    context_object_name = "kingdoms"

    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, "kingdom"):
            messages.info(
                request,
                "You need to create a kingdom before accessing diplomacy.",
            )
            return redirect("create_kingdom")

        kingdom = request.user.kingdom

        has_pending_war = (
            kingdom.wars_started.filter(
                status="pending_defender",
            ).exists()
            or kingdom.wars_received.filter(
                status="pending_defender",
            ).exists()
        )

        if has_pending_war:
            messages.info(
                request,
                "You must resolve the current war before accessing diplomacy.",
            )
            return redirect("dashboard")

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        my_kingdom = self.request.user.kingdom
        now = timezone.now()

        queryset = Kingdom.objects.exclude(
            id=my_kingdom.id,
        ).filter(
            war_available_until__gte=now,
        )

        my_strength = (
            my_kingdom.army_size
            * my_kingdom.army_quality
        )

        min_strength = my_strength * 0.65
        max_strength = my_strength * 1.45

        queryset = [
            kingdom
            for kingdom in queryset
            if min_strength
            <= kingdom.army_size * kingdom.army_quality
            <= max_strength
        ]

        blocked_defender_ids = set(
            WarCooldown.objects.filter(
                attacker=my_kingdom,
                cooldown_ends_at__gt=now,
            ).values_list(
                "defender_id",
                flat=True,
            )
        )

        queryset = [
            kingdom
            for kingdom in queryset
            if kingdom.id not in blocked_defender_ids
        ]

        return queryset

@login_required
def declare_war(request, slug):
    kingdom = getattr(request.user, "kingdom", None)

    if kingdom is None:
        messages.error(request, "You must have a kingdom to declare war.")
        return redirect("create_kingdom")

    enemy_kingdom = get_object_or_404(Kingdom, slug=slug)
    now = timezone.now()

    if enemy_kingdom == kingdom:
        messages.error(request, "You cannot declare war on your own kingdom.")
        return redirect("wars:diplomacy")

    if (
        enemy_kingdom.war_available_until is None
        or enemy_kingdom.war_available_until < now
    ):
        messages.error(request, "This kingdom is currently unavailable for war.")
        return redirect("wars:diplomacy")
    
    if kingdom.is_at_war is True:
        messages.error(request, "You cannot declare a war while you are still at war.")
        return redirect("wars:war_pending")
    
    if enemy_kingdom.is_at_war is True:
        messages.error(request, "This kingdom is currently at war and cannot be attacked.")
        return redirect("wars:diplomacy")

    attacker_strength = kingdom.army_size * kingdom.army_quality
    defender_strength = enemy_kingdom.army_size * enemy_kingdom.army_quality

    min_strength = attacker_strength * 0.65
    max_strength = attacker_strength * 1.45

    if defender_strength < min_strength:
        messages.error(request, "This kingdom is too weak for war.")
        return redirect("wars:diplomacy")

    if defender_strength > max_strength:
        messages.error(request, "This kingdom is too strong for war.")
        return redirect("wars:diplomacy")

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

    if enemy_kingdom.last_attacked_at and (now - enemy_kingdom.last_attacked_at).total_seconds() < 7200:
        messages.error(
            request,
            "You cannot declare war on this kingdom because it was attacked within the last two hours.",
        )
        return redirect("wars:diplomacy")

    if request.method == "POST":
        form = WarForm(request.POST)

        if form.is_valid():
            rallying_cry = form.cleaned_data["rallying_cry"].strip()
            ai_result = evaluate_rallying_cry(rallying_cry)

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
            enemy_kingdom.is_at_war = True
            enemy_kingdom.save(update_fields=["is_at_war"])
            kingdom.is_at_war = True
            kingdom.save(update_fields=["is_at_war"])

            return redirect("wars:war_pending")

    else:
        form = WarForm()

    momentum_hint = momentum_hint_for_kingdom(enemy_kingdom)

    return render(
        request,
        "wars/declare_war.html",
        {
            "form": form,
            "momentum_hint": momentum_hint,
            "enemy_kingdom": enemy_kingdom,
        },
    )

@login_required
def war_pending(request):
    if not hasattr(request.user, "kingdom"):
        messages.error(request, "You must have a kingdom to have declared a war.")
        return redirect("create_kingdom")
    
    kingdom = request.user.kingdom

    war = get_object_or_404(
        War,
        attacker=kingdom,
        status="pending_defender"
    )

    if war.status == "resolved":
        return redirect(
            "wars:battle_report",
             id=war.id,
        )

    if war.has_expired:
        resolve_war_simulation(
            war=war
        )

        return redirect(
            "wars:battle_report",
            id=war.id,
        )

    context = {
        "war": war,
        "kingdom": kingdom,
        "enemy_kingdom": war.defender,
    }

    return render(
        request,
        "wars/war_pending.html",
        context,
    )

@login_required
def notify_defender(request):
    if not hasattr(request.user, "kingdom"):
        messages.error(request, "You must have a kingdom to receive war notifications.")
        return redirect("create_kingdom")
    war = get_object_or_404(War, defender=request.user.kingdom, status="pending_defender")
    kingdom = request.user.kingdom
    enemy_kingdom = war.attacker
    if request.method == "POST":
        form = WarForm(request.POST)
        if form.is_valid():
            rallying_cry = form.cleaned_data["rallying_cry"].strip()
            war.defender_rallying_cry = rallying_cry
            ai_result = evaluate_rallying_cry(rallying_cry)
            war.defender_leadership_score = ai_result["leadership_score"]
            war.defender_inspiration_score = ai_result["inspiration_score"]
            war.defender_practicality_score = ai_result["practicality_score"]
            war.defender_rally_modifier = ai_result["rally_modifier"]
            war.defender_ai_feedback = ai_result["feedback"]
            war.save(update_fields=[
                "defender_rallying_cry",
                "defender_leadership_score",
                "defender_inspiration_score",
                "defender_practicality_score",
                "defender_rally_modifier",
                "defender_ai_feedback"
            ])
            return redirect("wars:notify_defender")
    else:
        form = WarForm(initial={
            "rallying_cry": war.defender_rallying_cry,
        })
    return render(request, "wars/war_notification.html", {
        "form": form,
        "war": war,
        "kingdom": kingdom,
        "enemy_kingdom": enemy_kingdom
    })

@login_required
@require_POST
def resolve_war(request):
    if not hasattr(request.user, "kingdom"):
        messages.error(request, "You must have a kingdom to resolve a war.")
        return redirect("create_kingdom")
    
    kingdom = request.user.kingdom

    war = get_object_or_404(War, defender=kingdom, status="pending_defender")

    
    resolve_war_simulation(war)
    return redirect(
        "wars:battle_report",
        id=war.id
    )
    
@login_required
def war_list(request):
    if not hasattr(request.user, "kingdom"):
        messages.error(request, "You must have a kingdom to view wars.")
        return redirect("create_kingdom")
    kingdom = request.user.kingdom
    is_at_war = kingdom.is_at_war
    wars_initiated = War.objects.filter(attacker=kingdom).order_by("-declared_at")
    wars_received = War.objects.filter(defender=kingdom).order_by("-declared_at")
    return render(request, "wars/my_wars.html", {
        "wars_initiated": wars_initiated,
        "wars_received": wars_received,
        "kingdom": kingdom,
        "is_at_war": is_at_war
    })

@login_required
def battle_report(request, id):
    if not hasattr(request.user, "kingdom"):
        messages.error(request, "You must have a kingdom to view battle reports.")
        return redirect("create_kingdom")
    kingdom = request.user.kingdom
    war = get_object_or_404(War, id=id)

    if war.attacker != kingdom and war.defender != kingdom:
        raise Http404()
    battle = war.battle
    was_unseen = True
    if battle.report_seen:
        was_unseen = False
    battle.report_seen = True
    battle.save(update_fields=["report_seen"])
    return render(request, "wars/battle_report.html", {
        "battle": battle,
        "war": war,
        "was_unseen": was_unseen
    })