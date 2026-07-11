from django.contrib import admin
from .models import War, Battle, WarCooldown

# Register your models here.

admin.site.register(War)
admin.site.register(Battle)
admin.site.register(WarCooldown)