from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import RideEventViewSet, RideViewSet, UserViewSet

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"rides", RideViewSet, basename="ride")
router.register(r"ride-events", RideEventViewSet, basename="rideevent")

urlpatterns = [
    path("", include(router.urls)),
]
