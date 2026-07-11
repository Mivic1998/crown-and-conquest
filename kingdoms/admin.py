from django.contrib import admin
from .models import Kingdom, TurnHistory, TurnLimit, Event

# Register your models here.

admin.site.register(Kingdom)
admin.site.register(TurnHistory)
admin.site.register(TurnLimit)
admin.site.register(Event)