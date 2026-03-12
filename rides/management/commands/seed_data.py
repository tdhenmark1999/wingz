import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from rides.models import Ride, RideEvent, User


class Command(BaseCommand):
    help = "Seed the database with sample data for development and testing"

    def handle(self, *args, **options):
        self.stdout.write("Seeding database...")

        # Create admin user
        admin, _ = User.objects.get_or_create(
            email="admin@wingz.com",
            defaults={
                "role": "admin",
                "first_name": "Admin",
                "last_name": "User",
                "phone_number": "+1234567890",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        admin.set_password("admin123")
        admin.save()

        # Create drivers
        drivers_data = [
            ("Chris", "H", "chris.h@wingz.com"),
            ("Howard", "Y", "howard.y@wingz.com"),
            ("Randy", "W", "randy.w@wingz.com"),
        ]
        drivers = []
        for first, last, email in drivers_data:
            driver, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "role": "driver",
                    "first_name": first,
                    "last_name": last,
                    "phone_number": f"+1555{random.randint(1000000, 9999999)}",
                },
            )
            drivers.append(driver)

        # Create riders
        riders = []
        for i in range(1, 11):
            rider, _ = User.objects.get_or_create(
                email=f"rider{i}@example.com",
                defaults={
                    "role": "rider",
                    "first_name": f"Rider{i}",
                    "last_name": f"Test",
                    "phone_number": f"+1555{random.randint(1000000, 9999999)}",
                },
            )
            riders.append(rider)

        # Create rides with ride events
        statuses = ["en-route", "pickup", "dropoff"]
        now = timezone.now()

        # Base coordinates (San Francisco area)
        base_lat, base_lon = 37.7749, -122.4194

        for i in range(50):
            ride_time = now - timedelta(
                days=random.randint(0, 120),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
            status = random.choice(statuses)
            driver = random.choice(drivers)
            rider = random.choice(riders)

            ride = Ride.objects.create(
                status=status,
                id_rider=rider,
                id_driver=driver,
                pickup_latitude=base_lat + random.uniform(-0.1, 0.1),
                pickup_longitude=base_lon + random.uniform(-0.1, 0.1),
                dropoff_latitude=base_lat + random.uniform(-0.1, 0.1),
                dropoff_longitude=base_lon + random.uniform(-0.1, 0.1),
                pickup_time=ride_time,
            )

            # Create ride events
            # "Status changed to pickup" event
            pickup_event_time = ride_time
            RideEvent.objects.create(
                id_ride=ride,
                description="Status changed to pickup",
                created_at=pickup_event_time,
            )

            if status in ("pickup", "dropoff"):
                # Duration between 20 min and 2 hours
                duration_minutes = random.randint(20, 120)
                dropoff_event_time = pickup_event_time + timedelta(
                    minutes=duration_minutes
                )
                RideEvent.objects.create(
                    id_ride=ride,
                    description="Status changed to dropoff",
                    created_at=dropoff_event_time,
                )

            # Add some recent events (within last 24 hours) for testing todays_ride_events
            if random.random() < 0.3:
                RideEvent.objects.create(
                    id_ride=ride,
                    description="Driver arrived at pickup",
                    created_at=now - timedelta(hours=random.randint(1, 23)),
                )

        self.stdout.write(self.style.SUCCESS(
            f"Seeded: {User.objects.count()} users, "
            f"{Ride.objects.count()} rides, "
            f"{RideEvent.objects.count()} ride events"
        ))
