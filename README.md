# Wingz Ride Management API

A RESTful API built with Django REST Framework for managing ride information.

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

## Authentication

All API endpoints require authentication with a user whose `role` is `"admin"`.

Use HTTP Basic Authentication or session-based auth via Django admin:

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

### Filtering

```
GET /api/rides/?status=pickup
GET /api/rides/?rider_email=rider1@example.com
GET /api/rides/?status=dropoff&rider_email=rider1@example.com
```

### Sorting

**By pickup time:**
```
GET /api/rides/?sort_by=pickup_time&order=asc
GET /api/rides/?sort_by=pickup_time&order=desc
```

**By distance to a GPS position:**
```
GET /api/rides/?sort_by=distance&latitude=37.7749&longitude=-122.4194&order=asc
```

### Pagination

```
GET /api/rides/?page=2&page_size=20
```

- Default page size: 10
- Maximum page size: 100
- Sorting and filtering work with pagination

## Design Decisions & Performance Notes

### Query Optimization (2-3 queries total)

The Ride List API is optimized to minimize database queries:

1. **Query 1 (Rides + Rider + Driver):** Uses `select_related("id_rider", "id_driver")` to fetch rides along with their related rider and driver in a single SQL JOIN query.

2. **Query 2 (Today's Ride Events):** Uses `Prefetch` with a filtered queryset to fetch only RideEvents from the last 24 hours. This avoids loading the entire (potentially very large) RideEvent table.

3. **Query 3 (Count for pagination):** Standard pagination count query.

This means the API executes only **2 queries** for data retrieval + **1 query** for the pagination count, regardless of how many rides are returned.

### `todays_ride_events` Field

Instead of returning all RideEvents for each Ride (which could be millions of records), the API returns a `todays_ride_events` field that contains only events from the last 24 hours. This is achieved using Django's `Prefetch` object with a filtered queryset, which adds a single prefetch query rather than N+1 queries.

### Distance Sorting Strategy

Since SQLite doesn't support native geospatial functions, distance calculation uses the Haversine formula in Python. For large datasets, the approach is:

1. Fetch only PKs + coordinates (lightweight query)
2. Compute distances and sort in Python
3. Paginate the sorted list
4. Fetch full objects only for the current page

For production with PostgreSQL, this would be replaced with PostGIS `ST_Distance` annotations for database-level sorting. The current approach still respects pagination and doesn't load all ride data into memory.

### Custom User Model

The project uses a custom User model extending `AbstractBaseUser` to match the assessment's User table schema (with `id_user` as PK, `role` field, etc.) while still being compatible with Django's auth system.

## Bonus SQL - Trips Over 1 Hour

The following raw SQL query returns the count of trips that took more than 1 hour from Pickup to Dropoff, grouped by Month and Driver.

The trip duration is calculated by finding the time difference between the "Status changed to pickup" and "Status changed to dropoff" RideEvents for each ride.

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

**PostgreSQL version** (for production):

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

### How It Works

- **Pickup time** is determined by the RideEvent with description "Status changed to pickup"
- **Dropoff time** is determined by the RideEvent with description "Status changed to dropoff"
- The query joins both events to the same ride, calculates the time difference, and filters for trips exceeding 1 hour
- Results are grouped by month (YYYY-MM format) and driver (first name + last initial)

## Project Structure

```
wingz/
├── manage.py
├── requirements.txt
├── README.md
├── wingz_project/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── rides/
    ├── __init__.py
    ├── admin.py
    ├── apps.py
    ├── filters.py
    ├── models.py
    ├── permissions.py
    ├── serializers.py
    ├── urls.py
    ├── views.py
    ├── migrations/
    │   └── __init__.py
    └── management/
        └── commands/
            └── seed_data.py
```
