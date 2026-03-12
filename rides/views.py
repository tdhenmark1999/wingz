import math

from django.db.models import F, Prefetch
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination

from .filters import RideFilter
from .models import Ride, RideEvent, User
from .serializers import (
    RideEventSerializer,
    RideListSerializer,
    RideSerializer,
    UserSerializer,
)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class RideEventViewSet(viewsets.ModelViewSet):
    queryset = RideEvent.objects.select_related("id_ride").all()
    serializer_class = RideEventSerializer


class RideListPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance in km between two GPS points using the Haversine formula."""
    R = 6371.0  # Earth radius in km
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


class RideViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Ride CRUD operations.

    Supports:
    - Filtering by `status` and `rider_email`
    - Sorting by `pickup_time` (sort_by=pickup_time)
    - Sorting by distance to pickup (sort_by=distance, requires latitude & longitude params)
    - Pagination

    Performance notes:
    - Uses select_related for rider and driver (single JOIN query)
    - Uses Prefetch with a filtered queryset for todays_ride_events
      (only RideEvents from the last 24 hours)
    - Total queries: 2 (rides + ride_events) + 1 for pagination count = 3
    """

    pagination_class = RideListPagination
    filterset_class = RideFilter

    def get_serializer_class(self):
        if self.action == "list":
            return RideListSerializer
        return RideSerializer

    def get_queryset(self):
        now = timezone.now()
        twenty_four_hours_ago = now - timezone.timedelta(hours=24)

        # Prefetch only today's ride events (last 24 hours) to avoid
        # loading the entire RideEvent table which could be very large.
        todays_events_prefetch = Prefetch(
            "ride_events",
            queryset=RideEvent.objects.filter(created_at__gte=twenty_four_hours_ago),
            to_attr="todays_ride_events",
        )

        queryset = (
            Ride.objects.select_related("id_rider", "id_driver")
            .prefetch_related(todays_events_prefetch)
        )

        # Apply sorting
        sort_by = self.request.query_params.get("sort_by", None)
        if sort_by == "pickup_time":
            order = self.request.query_params.get("order", "asc")
            if order == "desc":
                queryset = queryset.order_by("-pickup_time")
            else:
                queryset = queryset.order_by("pickup_time")

        elif sort_by == "distance":
            # Distance sorting requires latitude and longitude parameters.
            # We compute distance in Python after fetching from DB because:
            # 1. SQLite doesn't have native geo functions
            # 2. The assessment requires this to work with pagination
            # 3. For production with PostgreSQL, you'd use PostGIS annotations
            #
            # To maintain pagination correctness with distance sorting,
            # we use a two-pass approach:
            # - First, fetch all ride IDs sorted by distance
            # - Then re-query with the paginated ID set
            # This is handled in the list() method override below.
            pass

        return queryset

    def list(self, request, *args, **kwargs):
        sort_by = request.query_params.get("sort_by", None)

        if sort_by == "distance":
            return self._list_sorted_by_distance(request)

        return super().list(request, *args, **kwargs)

    def _list_sorted_by_distance(self, request):
        """
        Handle distance-based sorting efficiently.

        Strategy for large tables:
        1. Apply filters first to reduce the working set
        2. Fetch only the coordinates + PKs (lightweight query)
        3. Sort by computed distance in Python
        4. Paginate the sorted PKs
        5. Fetch full objects for only the current page
        """
        lat = request.query_params.get("latitude")
        lon = request.query_params.get("longitude")

        if lat is None or lon is None:
            from rest_framework.response import Response
            from rest_framework import status

            return Response(
                {"error": "latitude and longitude are required when sort_by=distance"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_lat = float(lat)
            user_lon = float(lon)
        except (ValueError, TypeError):
            from rest_framework.response import Response
            from rest_framework import status

            return Response(
                {"error": "latitude and longitude must be valid numbers"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order = request.query_params.get("order", "asc")

        # Step 1: Get filtered queryset with only PK + coordinates (lightweight)
        base_qs = Ride.objects.all()

        # Apply the same filters
        filterset = self.filterset_class(request.query_params, queryset=base_qs)
        if filterset.is_valid():
            base_qs = filterset.qs

        rides_coords = base_qs.values_list(
            "id_ride", "pickup_latitude", "pickup_longitude"
        )

        # Step 2: Compute distances and sort
        rides_with_distance = []
        for ride_id, p_lat, p_lon in rides_coords:
            dist = haversine_distance(user_lat, user_lon, p_lat, p_lon)
            rides_with_distance.append((ride_id, dist))

        rides_with_distance.sort(key=lambda x: x[1], reverse=(order == "desc"))

        # Step 3: Paginate the sorted IDs
        paginator = self.pagination_class()
        page_size = paginator.get_page_size(request)
        page_number = int(request.query_params.get(paginator.page_query_param, 1))
        total_count = len(rides_with_distance)

        start = (page_number - 1) * page_size
        end = start + page_size
        page_ids_ordered = [rid for rid, _ in rides_with_distance[start:end]]

        # Step 4: Fetch full objects for this page only (with prefetch)
        now = timezone.now()
        twenty_four_hours_ago = now - timezone.timedelta(hours=24)

        todays_events_prefetch = Prefetch(
            "ride_events",
            queryset=RideEvent.objects.filter(created_at__gte=twenty_four_hours_ago),
            to_attr="todays_ride_events",
        )

        rides_qs = (
            Ride.objects.filter(id_ride__in=page_ids_ordered)
            .select_related("id_rider", "id_driver")
            .prefetch_related(todays_events_prefetch)
        )

        # Preserve distance-based ordering
        rides_map = {r.id_ride: r for r in rides_qs}
        ordered_rides = [rides_map[rid] for rid in page_ids_ordered if rid in rides_map]

        serializer = RideListSerializer(ordered_rides, many=True)

        # Build paginated response
        from collections import OrderedDict
        from rest_framework.response import Response

        if total_count == 0:
            return Response(
                OrderedDict(
                    [("count", 0), ("next", None), ("previous", None), ("results", [])]
                )
            )

        # Build next/previous URLs
        base_url = request.build_absolute_uri(request.path)
        params = request.query_params.copy()

        next_url = None
        if end < total_count:
            params[paginator.page_query_param] = page_number + 1
            next_url = f"{base_url}?{params.urlencode()}"

        previous_url = None
        if page_number > 1:
            params[paginator.page_query_param] = page_number - 1
            previous_url = f"{base_url}?{params.urlencode()}"

        return Response(
            OrderedDict(
                [
                    ("count", total_count),
                    ("next", next_url),
                    ("previous", previous_url),
                    ("results", serializer.data),
                ]
            )
        )
