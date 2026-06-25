from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("create_kingdom/", views.create_kingdom, name="create_kingdom"),
]

