from django.urls import path
from . import views
from .views import KingdomLeaderboard

urlpatterns = [
    path("leaderboard/", views.KingdomLeaderboard.as_view(), name="leaderboard"),
     path('leaderboard/<slug:slug>/', views.kingdom_detail, name='kingdom_detail'),
]
