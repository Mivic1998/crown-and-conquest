from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("create_kingdom/", views.create_kingdom, name="create_kingdom"),
    path("take_turn/", views.take_turn, name="take_turn"),
    path("events/<int:event_id>/", views.respond_to_event, name="event_response")
]

