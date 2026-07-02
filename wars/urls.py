from django.urls import path
from . import views

urlpatterns = [
    path("diplomacy/", views.DiplomacyView.as_view(), name="diplomacy"),
    path("diplomacy/war/<slug:slug>/", views.declare_war, name="declare_war")
]