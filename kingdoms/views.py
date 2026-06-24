from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import PolicyForm
from .models import Kingdom

# Create your views here.

@login_required
def dashboard(request):
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
        "dashboard.html",
        {
            "kingdom": kingdom,
            "form": form,
        },
    )