"""Public-page, leaderboard, kingdom-profile, and account-management views.

This module contains the shared views that do not belong exclusively to the
kingdom simulation, warfare, or payments applications.

Its responsibilities include:

- rendering the public homepage and game-mechanics guide;
- calculating and displaying the global kingdom leaderboard;
- displaying public profiles for other kingdoms;
- securely deleting the authenticated user's account.

The leaderboard calculation is performed within the database query so that
kingdoms can be sorted before Django applies pagination. Account deletion is
protected by authentication and an exact confirmation phrase.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views import generic
from kingdoms.models import Kingdom
from django.db.models import F, Value, IntegerField, ExpressionWrapper
from django.db.models.functions import Cast


def home(request):
    """Render the public landing page.

    The view does not provide custom context. The template uses Django's
    standard ``request`` context, particularly ``user.is_authenticated`` and
    the user's optional reverse ``kingdom`` relationship, to choose the most
    appropriate call-to-action.

    Args:
        request: The Django HTTP request.

    Returns:
        A rendered ``core/home.html`` response.
    """
    # ``core/home.html`` receives the standard template context processors.
    # It uses the authenticated user state to show either registration/login,
    # kingdom creation, or dashboard navigation.
    return render(request, "core/home.html")


class KingdomLeaderboard(generic.ListView):
    """Display kingdoms ordered by a calculated realm score.

    ``ListView`` automatically evaluates the queryset, applies pagination, and
    supplies model-list context to the template.

    Because the model is ``Kingdom``, Django automatically provides both:

    - ``object_list``;
    - ``kingdom_list``.

    The current template uses ``kingdom_list``.

    Pagination additionally supplies ``page_obj``, ``paginator``, and
    ``is_paginated``, although the current template does not render controls
    using those values.
    """

    # The template iterates over the automatically generated ``kingdom_list``
    # context variable and displays each kingdom's rank, crest, identity, and
    # calculated statistics.
    template_name = "core/leaderboard.html"

    # Django returns no more than 25 kingdoms on a single page and automatically
    # supplies pagination metadata such as ``page_obj`` and ``paginator``.
    paginate_by = 25

    def get_queryset(self):
        """Return all kingdoms ordered by their calculated realm score.

        The score gives each territory 1,000 points and adds one point for
        every ten members of the population. It is calculated as a database
        annotation so ordering occurs before pagination.

        ``Cast`` converts the population contribution to an integer, matching
        the integer-style score displayed by the leaderboard.

        Returns:
            A queryset of ``Kingdom`` objects annotated with ``realm_score`` and
            ordered from highest to lowest score.
        """
        return (
            Kingdom.objects.annotate(
                # ``F`` expressions refer to model fields inside the database
                # query rather than loading every Kingdom into Python first.
                realm_score=ExpressionWrapper(
                    # Territory is deliberately weighted much more heavily than
                    # population within the overall leaderboard calculation.
                    (F("territory_count") * Value(1000))
                    + Cast(F("population") / Value(10), IntegerField()),

                    # Explicitly declare the result type so Django and the
                    # database treat the annotation as an integer expression.
                    output_field=IntegerField(),
                )
            )
            # Realm score is the primary ranking criterion. Territory and
            # population provide deterministic tie-breakers where scores match.
            .order_by("-realm_score", "-territory_count", "-population")
        )


def kingdom_detail(request, slug):
    """Display the public profile of another player's kingdom.

    A player viewing their own kingdom is redirected to the private dashboard,
    which contains more complete management information. Other kingdoms remain
    publicly viewable through their unique slug.

    Args:
        request: The Django HTTP request.
        slug: The unique URL slug identifying the requested kingdom.

    Returns:
        ``core/kingdom_detail.html`` for another kingdom, or a redirect to the
        dashboard when the authenticated user owns the requested kingdom.
    """
    # Start with the complete Kingdom queryset. ``get_object_or_404`` then
    # performs the slug lookup and returns a normal 404 response if no matching
    # public profile exists.
    queryset = Kingdom.objects.all()
    kingdom = get_object_or_404(queryset, slug=slug) #Checks whether a kingdom associated with the given slug exists, otherwise throws an error

    # Anonymous users and authenticated users without a kingdom receive None.
    # This avoids assuming that every account has completed kingdom creation.
    user_kingdom = getattr(request.user, "kingdom", None) 

    # Owners are directed to the management dashboard rather than being shown
    # the restricted public version of their own kingdom profile.
    if kingdom == user_kingdom:
        return redirect("dashboard") #Visiting your own kingdom redirects you to the dashboard
    else:
        return render(
            request,
            "core/kingdom_detail.html",
            {
                # The template uses this object to display the crest, name,
                # premium badge, ruler, leaderboard score, population, army
                # statistics, territory count, current turn, and war status.
                #
                # For authenticated visitors, the slug is also used to construct
                # a Declare War link when the kingdom is not currently at war.
                "kingdom": kingdom,
            },
        )


@login_required
def delete_account(request):
    """Permanently delete the authenticated user's account after confirmation.

    The view requires the exact phrase ``DELETE ACCOUNT`` before deletion.
    Because the Kingdom model owns a one-to-one relationship to Django's User
    model with ``on_delete=models.CASCADE``, deleting the user also removes the
    associated kingdom and dependent gameplay records through their cascading
    relationships.

    The user is logged out before deletion so the session does not continue to
    reference an account that no longer exists.

    Args:
        request: The authenticated Django HTTP request.

    Returns:
        ``core/delete_account.html`` for GET or invalid confirmation, otherwise
        a redirect to the homepage with a success message.
    """
    if request.method == "POST":

        # Read the raw confirmation value and remove surrounding whitespace.
        # The comparison remains case-sensitive and requires an exact phrase.
        confirmation = request.POST.get(
            "confirmation",
            ""
        ).strip()

        if confirmation != "DELETE ACCOUNT":
            return render(
                request,
                "core/delete_account.html",
                {
                    # The template displays this message directly beneath the
                    # confirmation input while leaving the destructive form
                    # available for correction.
                    "error": (
                        "You must type "
                        "DELETE ACCOUNT exactly "
                        "to confirm."
                    )
                }
            )

        # Preserve the username before deletion so it remains available for the
        # farewell message after the User object has been removed.
        username = request.user.username

        # Keep a local reference because ``logout`` replaces the authenticated
        # request user with an anonymous user.
        user = request.user

        # End the authenticated session before deleting the account it refers to.
        logout(request)

        # Deleting the User cascades to the owned Kingdom and then to related
        # gameplay records whose foreign keys also use cascading deletion.
        user.delete() #Logout is initiated first and the user's account is subsequently deleted, accompanied by a success message including the user's name

        # Django's messages framework stores this notice for display by the base
        # template after the redirect to the homepage.
        messages.success(
            request,
            f"Farewell, {username}. "
            "Your account has been permanently deleted."
        )

        # Redirect-after-POST prevents browser refresh from attempting to repeat
        # the destructive account-deletion request.
        return redirect("home")

    # On GET, the template displays the warning, list of data that will be
    # removed, CSRF-protected confirmation form, and cancellation link.
    return render(
        request,
        "core/delete_account.html",
    )


def mechanics(request):
    """Render the public gameplay-mechanics guide.

    The template is static and requires no view-specific context. It explains
    policies, turns, events, AI evaluation, warfare, hidden modifiers, reports,
    premium functionality, and general strategic principles.

    Args:
        request: The Django HTTP request.

    Returns:
        A rendered ``core/mechanics.html`` response.
    """
    return render(request, "core/mechanics.html")