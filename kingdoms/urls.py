from django.urls import path
from . import views

path("dashboard/", views.dashboard, name="dashboard"),