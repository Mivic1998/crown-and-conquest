from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from kingdoms.models import Kingdom
from .models import WarCooldown
from .forms import WarForm


# Create your views here.

class DiplomacyView(LoginRequiredMixin, ListView):
    model = Kingdom
    template_name = "wars/diplomacy.html"
    context_object_name = "kingdoms"

    def get_queryset(self):
        my_kingdom = self.request.user.kingdom
        now = timezone.now()

        queryset = Kingdom.objects.exclude(
            id=my_kingdom.id
        ).filter(
            war_available_until__gte=now
        )

        # Strength range filter
        my_strength = my_kingdom.army_size * my_kingdom.army_quality

        min_strength = my_strength * 0.65
        max_strength = my_strength * 1.45

        queryset = [
            kingdom for kingdom in queryset
            if min_strength <= kingdom.army_size * kingdom.army_quality <= max_strength
        ]

        # Cooldown filter
        blocked_defender_ids = WarCooldown.objects.filter(
            attacker=my_kingdom,
            cooldown_ends_at__gt=now,
        ).values_list("defender_id", flat=True)

        queryset = [
            kingdom for kingdom in queryset
            if kingdom.id not in blocked_defender_ids
        ]

        return queryset

@login_required
def declare_war(request, slug):
    kingdom = getattr(request.user, "kingdom", None)
    if kingdom is None:
        messages.error(request, "You must have a kingdom to declare war.")
        return redirect("kingdom:create_kingdom")
    enemy_kingdom = get_object_or_404(Kingdom, slug=slug)
    if enemy_kingdom == kingdom:
        messages.error(request, "You cannot declare war on your own kingdom.")
        return redirect("wars:diplomacy")
    elif enemy_kingdom.war_available_until < timezone.now():
        messages.error(request, "This kingdom is currently unavailable for war.")
        return redirect("wars:diplomacy")
    elif kingdom.army_size * kingdom.army_quality < enemy_kingdom.army_size * enemy_kingdom.army_quality * 0.65:
        messages.error(request, "This kingdom is too strong for war.")
        return redirect("wars:diplomacy")
    elif kingdom.army_size * kingdom.army_quality > enemy_kingdom.army_size * enemy_kingdom.army_quality * 1.45:
        messages.error(request, "This kingdom is too weak for war.")
        return redirect("wars:diplomacy")
    elif WarCooldown.objects.filter(attacker=kingdom, defender=enemy_kingdom, cooldown_ends_at__gt=timezone.now()).exists():
        messages.error(request, "You cannot declare war on this kingdom due to a cooldown.")
        return redirect("wars:diplomacy")
    elif enemy_kingdom.war_available_until < timezone.now():
        messages.error(request, "This kingdom is currently inactive and cannot be attacked.")
        return redirect("wars:diplomacy")
    if request.method == "POST":
        form = WarForm(request.POST)
        if(form.is_valid()):
            print
