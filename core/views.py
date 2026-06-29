from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views import generic
from kingdoms.models import Kingdom

# Create your views here.

class KingdomLeaderboard(generic.ListView):
    queryset = Kingdom.objects.order_by("-population")
    template_name = "core/leaderboard.html"
    paginate_by = 25

def kingdom_detail(request, slug):

    queryset = Kingdom.objects.all()
    kingdom = get_object_or_404(queryset, slug=slug)
    
    user_kingdom = getattr(request.user, "kingdom", None)

    if kingdom == user_kingdom:
        return redirect("dashboard")
    else: 
        return render(
        request,
        "core/kingdom_detail.html",
        {
            "kingdom": kingdom,
        },
    )

@login_required
def delete_account(request):

    if request.method == "POST":

        confirmation = request.POST.get(
            "confirmation",
            ""
        ).strip()

        if confirmation != "DELETE ACCOUNT":
            return render(
                request,
                "core/delete_account.html",
                {
                    "error": (
                        "You must type "
                        "DELETE ACCOUNT exactly "
                        "to confirm."
                    )
                }
            )

        username = request.user.username

        user = request.user

        logout(request)

        user.delete()

        messages.success(
            request,
            f"Farewell, {username}. "
            "Your account has been permanently deleted."
        )

        return redirect("home")

    return render(
        request,
        "core/delete_account.html",
    )
        
