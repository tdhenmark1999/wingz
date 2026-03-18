# Wingz Ride Management API

A RESTful API built with Django REST Framework for managing ride information, including ride tracking, driver/rider management, and ride event logging.

## Table of Contents

- [Setup](#setup)
- [Authentication](#authentication)
- [API Endpoints](#api-endpoints)
- [Ride List API Features](#ride-list-api-features)
- [Design Decisions & Performance Notes](#design-decisions--performance-notes)
- [Testing](#testing)
- [Bonus SQL - Trips Over 1 Hour](#bonus-sql---trips-over-1-hour)
- [Project Structure](#project-structure)

## Setup

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd wingz

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py makemigrations
python manage.py migrate

# Seed the database with sample data
python manage.py seed_data

# Run the development server
python manage.py runserver
```

### Admin Credentials (after seeding)

- **Email:** admin@wingz.com
- **Password:** admin123

### Running Tests

```bash
source venv/bin/activate
python manage.py test rides -v 2
```

All 20 tests should pass, covering authentication, CRUD operations, filtering, sorting, pagination, and query performance.

## Authentication

All API endpoints require authentication with a user whose `role` is `"admin"`.

A custom permission class `IsAdminRole` (`rides/permissions.py`) checks three conditions:
1. The user is present in the request
2. The user is authenticated
3. The user's `role` field equals `"admin"`

This permission is set as the **default permission class** in `wingz_project/settings.py`, so it applies globally to all endpoints without needing to specify it per view.

**Usage:**

```bash
# Basic Auth example
curl -u admin@wingz.com:admin123 http://localhost:8000/api/rides/
```

Or log in via the Django admin at `/admin/` first, then use the DRF browsable API.

## API Endpoints

### Users
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/users/` | List all users |
| POST | `/api/users/` | Create a user |
| GET | `/api/users/{id}/` | Retrieve a user |
| PUT | `/api/users/{id}/` | Update a user |
| DELETE | `/api/users/{id}/` | Delete a user |

### Rides
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/rides/` | List all rides (with nested data) |
| POST | `/api/rides/` | Create a ride |
| GET | `/api/rides/{id}/` | Retrieve a ride |
| PUT | `/api/rides/{id}/` | Update a ride |
| DELETE | `/api/rides/{id}/` | Delete a ride |

### Ride Events
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ride-events/` | List all ride events |
| POST | `/api/ride-events/` | Create a ride event |
| GET | `/api/ride-events/{id}/` | Retrieve a ride event |
| PUT | `/api/ride-events/{id}/` | Update a ride event |
| DELETE | `/api/ride-events/{id}/` | Delete a ride event |

## Ride List API Features

The `GET /api/rides/` endpoint is the core of this project. It returns a paginated list of rides with nested rider, driver, and today's ride event data — all optimized for minimal database queries.

### Filtering

Filter rides by status (exact match) or rider email (case-insensitive):

```
GET /api/rides/?status=pickup
GET /api/rides/?rider_email=rider1@example.com
GET /api/rides/?status=dropoff&rider_email=rider1@example.com
```

Filtering is implemented using `django-filter` with a custom `RideFilter` class (`rides/filters.py`) that maps query parameters to model field lookups.

### Sorting

Both sorting options are available in the same API via the `sort_by` query parameter.

**By pickup time** (database-level sorting):
```
GET /api/rides/?sort_by=pickup_time&order=asc
GET /api/rides/?sort_by=pickup_time&order=desc
```

**By distance to a GPS position** (Haversine formula):
```
GET /api/rides/?sort_by=distance&latitude=37.7749&longitude=-122.4194&order=asc
```

The `latitude` and `longitude` parameters are required when using `sort_by=distance`. The API returns a `400 Bad Request` with a clear error message if they are missing or invalid.

### Pagination

```
GET /api/rides/?page=2&page_size=20
```

- Default page size: 10
- Maximum page size: 100
- Pagination works correctly with both sorting and filtering

## Design Decisions & Performance Notes

### Query Optimization (2-3 queries total)

The Ride List API is optimized to minimize database queries, as required by the assessment:

1. **Query 1 — Rides + Rider + Driver (SQL JOIN):** Uses `select_related("id_rider", "id_driver")` to fetch rides along with their related rider and driver in a **single SQL JOIN query**. Without this, each ride would trigger 2 additional queries to fetch the rider and driver (N+1 problem).

2. **Query 2 — Today's Ride Events (Prefetch):** Uses Django's `Prefetch` object with a **filtered queryset** to fetch only RideEvents created in the last 24 hours. This is stored in the `todays_ride_events` attribute on each ride. The key optimization here is that it executes a **single additional query** with an `IN` clause for all ride IDs on the current page, rather than one query per ride.

3. **Query 3 — Count (Pagination):** Standard `COUNT(*)` query required by DRF's `PageNumberPagination` to calculate total pages.

**Result:** The API executes only **2 queries for data** + **1 query for pagination count** = **3 queries total**, regardless of how many rides are on the page. This is verified by a test using `assertNumQueries(3)`.

### `todays_ride_events` Field

The assessment states that the RideEvent table will be very large. Instead of returning all RideEvents for each Ride (which could be millions of records and cause severe performance issues), the API returns a `todays_ride_events` field containing **only events from the last 24 hours**.

This is achieved using Django's `Prefetch` object:
```python
Prefetch(
    "ride_events",
    queryset=RideEvent.objects.filter(created_at__gte=twenty_four_hours_ago),
    to_attr="todays_ride_events",
)
```

The `to_attr` parameter stores the prefetched results as a Python list attribute, and the filtered queryset ensures only recent events are loaded from the database.

### Two Serializers for Ride

The project uses two separate serializers for the Ride model:

- **`RideSerializer`** — Used for `create`, `update`, `retrieve`, and `delete` operations. Accepts foreign key IDs (integers) for `id_rider` and `id_driver`.
- **`RideListSerializer`** — Used only for the `list` action. Returns nested `UserSerializer` objects for rider/driver and includes `todays_ride_events`. This serializer reads from the prefetched data to avoid additional queries.

This separation is handled in the ViewSet's `get_serializer_class()` method.

### Distance Sorting Strategy

Since SQLite doesn't support native geospatial functions (like PostGIS's `ST_Distance`), distance calculation uses the **Haversine formula** in Python. The challenge was implementing this efficiently for large tables while maintaining correct pagination.

**Two-pass approach:**

1. **Pass 1 (Lightweight):** Fetch only `id_ride`, `pickup_latitude`, and `pickup_longitude` using `values_list()`. Apply filters first to reduce the working set.
2. **Compute & Sort:** Calculate Haversine distance for each ride and sort in Python.
3. **Paginate IDs:** Slice the sorted ID list based on the requested page number and page size.
4. **Pass 2 (Full objects):** Fetch complete ride objects (with `select_related` and `Prefetch`) only for the IDs on the current page.

This ensures that even with millions of rides, we only load full data for the rides on the current page (default 10). The response format matches DRF's standard pagination (`count`, `next`, `previous`, `results`).

**For production with PostgreSQL**, this would be replaced with PostGIS `ST_Distance` annotations for database-level sorting, which would be more efficient.

### Custom User Model

The project uses a custom User model (`rides/models.py`) extending `AbstractBaseUser` and `PermissionsMixin` to match the assessment's User table schema with:
- `id_user` as the primary key (instead of Django's default `id`)
- `role` field for role-based access control
- `email` as the `USERNAME_FIELD` (instead of `username`)
- Custom `UserManager` for `create_user` and `create_superuser`

The custom `db_table = "user"` and `db_column` settings on foreign keys ensure the generated database schema matches the assessment's table definitions exactly.

### Database Indexes

Indexes are added on frequently queried fields to improve performance:

**Ride table:**
- `status` — used for filtering
- `pickup_time` — used for sorting
- `id_rider` — used for filtering by rider email (JOIN)
- `id_driver` — used for driver lookups

**RideEvent table:**
- `created_at` — used for the 24-hour filter in `todays_ride_events`
- `id_ride` — used for the prefetch JOIN

## Testing

The test suite (`rides/tests.py`) contains **20 tests across 9 test classes**:

| Test Class | Tests | What It Verifies |
|---|---|---|
| `AuthenticationTest` | 3 | Unauthenticated users get 403, non-admin users get 403, admin users get 200 |
| `RideListTest` | 3 | Rides are returned, nested rider/driver data is included, `todays_ride_events` only contains events from the last 24 hours |
| `RideFilterTest` | 3 | Filtering by status, by rider email, and combined filtering |
| `RideSortingTest` | 4 | Sorting by pickup_time (asc/desc), sorting by distance, error handling for missing params |
| `RidePaginationTest` | 2 | Pagination response format (count/next/previous/results), custom `page_size` parameter |
| `RideQueryPerformanceTest` | 1 | Verifies the Ride List API uses exactly 3 database queries via `assertNumQueries(3)` |
| `UserCRUDTest` | 2 | List and retrieve users |
| `RideEventCRUDTest` | 2 | List and retrieve ride events |

## Bonus SQL - Trips Over 1 Hour

The following raw SQL query returns the count of trips that took more than 1 hour from Pickup to Dropoff, grouped by Month and Driver.

The trip duration is calculated by finding the time difference between the "Status changed to pickup" and "Status changed to dropoff" RideEvents for each ride.

### SQLite Version

```sql
SELECT
    strftime('%Y-%m', pickup_event.created_at) AS month,
    u.first_name || ' ' || substr(u.last_name, 1, 1) AS driver,
    COUNT(*) AS "count_of_trips_gt_1hr"
FROM ride r
JOIN "user" u ON r.id_driver = u.id_user
JOIN ride_event pickup_event
    ON pickup_event.id_ride = r.id_ride
    AND pickup_event.description = 'Status changed to pickup'
JOIN ride_event dropoff_event
    ON dropoff_event.id_ride = r.id_ride
    AND dropoff_event.description = 'Status changed to dropoff'
WHERE
    (julianday(dropoff_event.created_at) - julianday(pickup_event.created_at)) * 24 > 1
GROUP BY month, u.id_user
ORDER BY month, driver;
```

### PostgreSQL Version (for production)

```sql
SELECT
    TO_CHAR(pickup_event.created_at, 'YYYY-MM') AS month,
    u.first_name || ' ' || LEFT(u.last_name, 1) AS driver,
    COUNT(*) AS "count_of_trips_gt_1hr"
FROM ride r
JOIN "user" u ON r.id_driver = u.id_user
JOIN ride_event pickup_event
    ON pickup_event.id_ride = r.id_ride
    AND pickup_event.description = 'Status changed to pickup'
JOIN ride_event dropoff_event
    ON dropoff_event.id_ride = r.id_ride
    AND dropoff_event.description = 'Status changed to dropoff'
WHERE
    EXTRACT(EPOCH FROM (dropoff_event.created_at - pickup_event.created_at)) / 3600 > 1
GROUP BY month, u.id_user, driver
ORDER BY month, driver;
```

### How the SQL Works

1. **JOINs:** The `ride` table is joined with two instances of `ride_event` — one for the pickup event and one for the dropoff event — matched by `id_ride` and the event `description`.
2. **Duration Calculation:** The time difference between the dropoff and pickup event timestamps is computed. In SQLite, `julianday()` converts to fractional days (multiplied by 24 for hours). In PostgreSQL, `EXTRACT(EPOCH FROM ...)` gives seconds (divided by 3600 for hours).
3. **Filtering:** Only trips where the duration exceeds 1 hour are included.
4. **Grouping:** Results are grouped by month (`YYYY-MM` format) and driver (`id_user`), with the driver name displayed as first name + last initial.
5. **Two versions are provided** because SQLite and PostgreSQL have different date/time functions. The SQLite version is used for development; the PostgreSQL version is for production.

## Project Structure

```
wingz/
├── manage.py                  # Django management script
├── requirements.txt           # Python dependencies
├── README.md                  # This file
├── db.sqlite3                 # SQLite database (created after migrate)
├── wingz_project/
│   ├── __init__.py
│   ├── settings.py            # Django & DRF configuration
│   ├── urls.py                # Root URL configuration
│   └── wsgi.py                # WSGI entry point
└── rides/
    ├── __init__.py
    ├── admin.py               # Django admin registration
    ├── apps.py                # App configuration
    ├── filters.py             # RideFilter (django-filter)
    ├── models.py              # User, Ride, RideEvent models
    ├── permissions.py         # IsAdminRole permission class
    ├── serializers.py         # DRF serializers
    ├── tests.py               # Test suite (20 tests)
    ├── urls.py                # API URL routing (DRF router)
    ├── views.py               # ViewSets with query optimization
    ├── migrations/
    │   ├── __init__.py
    │   ├── 0001_initial.py
    │   └── 0002_alter_ride_options_alter_rideevent_options_and_more.py
    └── management/
        └── commands/
            └── seed_data.py   # Database seeder (50 rides, 14 users)
```
