from django.urls import path
from . import views
from .views import DiplomacyView, declare_war, war_pending, notify_defender, resolve_war, war_list, battle_report

app_name = "wars"

urlpatterns = [
    path("", views.war_list, name="war_list"),
    path("diplomacy/", views.DiplomacyView.as_view(), name="diplomacy"),
    path("declare/<slug:slug>/", views.declare_war, name="declare_war"),
    path("pending/", views.war_pending, name="war_pending"),
    path("notify/", views.notify_defender, name="notify_defender"),
    path("report/<int:id>/", views.battle_report, name="battle_report"),
    path("resolve_war/", views.resolve_war, name="resolve_war")
]