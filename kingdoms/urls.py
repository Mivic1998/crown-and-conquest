from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("create_kingdom/", views.create_kingdom, name="create_kingdom"),
    path("take_turn/", views.take_turn, name="take_turn"),
    path("events/<int:event_id>/respond/", views.respond_to_event, name="event_response"),
    path("events/", views.EventHistoryListView.as_view(), name="event_history"),
    path("events/<int:event_id>/", views.event_detail, name="event_detail"),
    path("history/", views.TurnHistoryListView.as_view(), name="turn_history"),
    path("history/<int:turn_id>/", views.turn_detail, name="turn_detail"),
    path("settings/", views.kingdom_settings, name="kingdom_settings"),
    path("delete/", views.delete_kingdom, name="delete_kingdom")
]

