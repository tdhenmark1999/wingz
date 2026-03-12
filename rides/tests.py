from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .models import Ride, RideEvent, User


class BaseTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create admin user
        self.admin = User.objects.create_user(
            email="admin@test.com",
            password="admin123",
            first_name="Admin",
            last_name="User",
            role="admin",
        )
        self.admin.is_staff = True
        self.admin.save()

        # Create non-admin user
        self.regular_user = User.objects.create_user(
            email="user@test.com",
            password="user123",
            first_name="Regular",
            last_name="User",
            role="rider",
        )

        # Create a driver
        self.driver = User.objects.create_user(
            email="driver@test.com",
            password="driver123",
            first_name="Chris",
            last_name="H",
            role="driver",
        )

        # Create a rider
        self.rider = User.objects.create_user(
            email="rider@test.com",
            password="rider123",
            first_name="Rider",
            last_name="One",
            role="rider",
        )

        now = timezone.now()

        # Create rides
        self.ride1 = Ride.objects.create(
            status="pickup",
            id_rider=self.rider,
            id_driver=self.driver,
            pickup_latitude=37.7749,
            pickup_longitude=-122.4194,
            dropoff_latitude=37.8049,
            dropoff_longitude=-122.4094,
            pickup_time=now - timedelta(hours=2),
        )
        self.ride2 = Ride.objects.create(
            status="dropoff",
            id_rider=self.rider,
            id_driver=self.driver,
            pickup_latitude=37.8000,
            pickup_longitude=-122.4300,
            dropoff_latitude=37.8200,
            dropoff_longitude=-122.4100,
            pickup_time=now - timedelta(hours=5),
        )
        self.ride3 = Ride.objects.create(
            status="en-route",
            id_rider=self.rider,
            id_driver=self.driver,
            pickup_latitude=40.7128,
            pickup_longitude=-74.0060,
            dropoff_latitude=40.7300,
            dropoff_longitude=-74.0000,
            pickup_time=now + timedelta(hours=1),
        )

        # Create ride events — some within last 24h, some older
        self.event1 = RideEvent.objects.create(
            id_ride=self.ride1,
            description="Status changed to pickup",
            created_at=now - timedelta(hours=2),
        )
        self.event2 = RideEvent.objects.create(
            id_ride=self.ride1,
            description="Status changed to dropoff",
            created_at=now - timedelta(hours=1),
        )
        self.event_old = RideEvent.objects.create(
            id_ride=self.ride2,
            description="Status changed to pickup",
            created_at=now - timedelta(days=5),
        )


class AuthenticationTest(BaseTestCase):
    """Test that only admin role users can access the API."""

    def test_unauthenticated_access_denied(self):
        response = self.client.get("/api/rides/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_admin_access_denied(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get("/api/rides/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_access_allowed(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/rides/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class RideListTest(BaseTestCase):
    """Test the Ride List API including nested data."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.admin)

    def test_ride_list_returns_rides(self):
        response = self.client.get("/api/rides/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)

    def test_ride_list_includes_nested_rider_and_driver(self):
        response = self.client.get("/api/rides/")
        ride = response.data["results"][0]
        # Should have nested rider and driver objects
        self.assertIn("id_rider", ride)
        self.assertIn("id_driver", ride)
        self.assertIn("email", ride["id_rider"])
        self.assertIn("first_name", ride["id_driver"])

    def test_ride_list_includes_todays_ride_events(self):
        response = self.client.get("/api/rides/")
        results = response.data["results"]
        # Find ride1 — it has events within 24h
        ride1_data = next(r for r in results if r["id_ride"] == self.ride1.id_ride)
        self.assertIn("todays_ride_events", ride1_data)
        # ride1 has 2 events within 24h
        self.assertEqual(len(ride1_data["todays_ride_events"]), 2)

        # Find ride2 — its event is 5 days old, should be empty
        ride2_data = next(r for r in results if r["id_ride"] == self.ride2.id_ride)
        self.assertEqual(len(ride2_data["todays_ride_events"]), 0)


class RideFilterTest(BaseTestCase):
    """Test filtering by status and rider email."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.admin)

    def test_filter_by_status(self):
        response = self.client.get("/api/rides/", {"status": "pickup"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["status"], "pickup")

    def test_filter_by_rider_email(self):
        response = self.client.get("/api/rides/", {"rider_email": "rider@test.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)

    def test_filter_by_status_and_email(self):
        response = self.client.get(
            "/api/rides/",
            {"status": "en-route", "rider_email": "rider@test.com"},
        )
        self.assertEqual(response.data["count"], 1)


class RideSortingTest(BaseTestCase):
    """Test sorting by pickup_time and distance."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.admin)

    def test_sort_by_pickup_time_asc(self):
        response = self.client.get(
            "/api/rides/", {"sort_by": "pickup_time", "order": "asc"}
        )
        results = response.data["results"]
        times = [r["pickup_time"] for r in results]
        self.assertEqual(times, sorted(times))

    def test_sort_by_pickup_time_desc(self):
        response = self.client.get(
            "/api/rides/", {"sort_by": "pickup_time", "order": "desc"}
        )
        results = response.data["results"]
        times = [r["pickup_time"] for r in results]
        self.assertEqual(times, sorted(times, reverse=True))

    def test_sort_by_distance(self):
        # Sort from San Francisco coords — ride1 and ride2 are in SF, ride3 is in NYC
        response = self.client.get(
            "/api/rides/",
            {
                "sort_by": "distance",
                "latitude": "37.7749",
                "longitude": "-122.4194",
                "order": "asc",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        # ride1 is closest (same coords), ride3 (NYC) should be last
        self.assertEqual(results[-1]["id_ride"], self.ride3.id_ride)

    def test_sort_by_distance_missing_params(self):
        response = self.client.get("/api/rides/", {"sort_by": "distance"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class RidePaginationTest(BaseTestCase):
    """Test pagination works with sorting and filtering."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.admin)

    def test_pagination_response_format(self):
        response = self.client.get("/api/rides/")
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        self.assertIn("results", response.data)

    def test_page_size_param(self):
        response = self.client.get("/api/rides/", {"page_size": 1})
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIsNotNone(response.data["next"])


class RideQueryPerformanceTest(BaseTestCase):
    """Test that the Ride List API uses minimal queries."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.admin)

    def test_ride_list_query_count(self):
        """Should use at most 3 queries: rides+joins, prefetch events, count."""
        from django.test.utils import override_settings

        with self.assertNumQueries(3):
            self.client.get("/api/rides/")


class UserCRUDTest(BaseTestCase):
    """Test User ViewSet CRUD operations."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.admin)

    def test_list_users(self):
        response = self.client.get("/api/users/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_user(self):
        response = self.client.get(f"/api/users/{self.admin.id_user}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "admin@test.com")


class RideEventCRUDTest(BaseTestCase):
    """Test RideEvent ViewSet CRUD operations."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.admin)

    def test_list_ride_events(self):
        response = self.client.get("/api/ride-events/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_ride_event(self):
        response = self.client.get(
            f"/api/ride-events/{self.event1.id_ride_event}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["description"], "Status changed to pickup")
