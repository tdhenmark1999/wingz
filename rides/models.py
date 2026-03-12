from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", "admin")
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id_user = models.AutoField(primary_key=True)
    role = models.CharField(max_length=50, default="user")
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=50, blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        db_table = "user"
        ordering = ["id_user"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Ride(models.Model):
    id_ride = models.AutoField(primary_key=True)
    status = models.CharField(
        max_length=50,
        choices=[
            ("en-route", "En Route"),
            ("pickup", "Pickup"),
            ("dropoff", "Dropoff"),
        ],
    )
    id_rider = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="rides_as_rider",
        db_column="id_rider",
    )
    id_driver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="rides_as_driver",
        db_column="id_driver",
    )
    pickup_latitude = models.FloatField()
    pickup_longitude = models.FloatField()
    dropoff_latitude = models.FloatField()
    dropoff_longitude = models.FloatField()
    pickup_time = models.DateTimeField()

    class Meta:
        db_table = "ride"
        ordering = ["-pickup_time"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["pickup_time"]),
            models.Index(fields=["id_rider"]),
            models.Index(fields=["id_driver"]),
        ]

    def __str__(self):
        return f"Ride {self.id_ride} ({self.status})"


class RideEvent(models.Model):
    id_ride_event = models.AutoField(primary_key=True)
    id_ride = models.ForeignKey(
        Ride,
        on_delete=models.CASCADE,
        related_name="ride_events",
        db_column="id_ride",
    )
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField()

    class Meta:
        db_table = "ride_event"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["id_ride"]),
        ]

    def __str__(self):
        return f"RideEvent {self.id_ride_event}: {self.description}"
