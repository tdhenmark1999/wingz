from django.contrib import admin

from .models import Ride, RideEvent, User

admin.site.register(User)
admin.site.register(Ride)
admin.site.register(RideEvent)
