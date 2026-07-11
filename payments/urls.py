from django.urls import path
from . import views
from .views import pricing, create_checkout_session, subscription_success, subscription_cancel, stripe_webhook, handle_checkout_completed, handle_subscription_updated

app_name = "payments"

urlpatterns = [
    path("pricing/", views.pricing, name="pricing"),
    path("checkout/", views.create_checkout_session, name="checkout"),
    path("success/", views.subscription_success, name="success"),
    path("cancel/", views.subscription_cancel, name="cancel"),
    path("webhook/", views.stripe_webhook, name="webhook"),
]