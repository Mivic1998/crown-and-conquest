from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("create_kingdom/", views.create_kingdom, name="create_kingdom"),
    path("take_turn/", views.take_turn, name="take_turn"),
    path("event/<int:event_id>/respond/", views.respond_to_event, name="event_response"),
    path("event/", views.event_detail, name="event_history"),
    path("event/<int:event_id>/", views.event_detail, name="event_detail"),
    path("history/", views.turn_history, name="turn_history"),
    path("history/<int:turn_id>/", views.turn_detail, name="turn_detail")
]

