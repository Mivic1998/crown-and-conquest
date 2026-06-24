from django.shortcuts import render, get_object_or_404
from django.views import generic
from kingdoms.models import Kingdom

# Create your views here.

class KingdomLeaderboard(generic.ListView):
    queryset = Kingdom.objects.order_by(-population)
    template_name = leaderboard.html
    paginate_by = 25

def kingdom_detail(request, slug):
    queryset = Kingdom.objects.all()
    kingdom = get_object_or_404(queryset, slug=slug)
    return render(
        request,
        "core/kingdom_detail.html",
        {
            "kingdom": kingdom,
        },
    )
