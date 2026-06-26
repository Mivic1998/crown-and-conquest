from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("create_kingdom/", views.create_kingdom, name="create_kingdom"),
    path("take_turn/", views.take_turn, name="take_turn"),
    path("famine_event/", views.famine_event, name="famine_event"),
]

