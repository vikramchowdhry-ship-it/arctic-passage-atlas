"""Distance bounds used to document provider caveats that depend on distance from shore."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_M = 6_371_008.8
METRES_PER_NAUTICAL_MILE = 1852.0


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    phi1, phi2 = radians(lat1), radians(lat2)
    a = sin((phi2 - phi1) / 2) ** 2 + cos(phi1) * cos(phi2) * sin(radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def max_distance_to_point_nmi(bbox: tuple[float, float, float, float], lon: float, lat: float) -> float:
    """Largest distance from a point inside `bbox` to any location in it.

    If (lon, lat) is a land location, every point in the box is at most this far from shore. The
    true nearest-coast distance is smaller. The farthest point of a lon/lat box from an interior
    point is always a corner, so four corners are enough.
    """
    west, south, east, north = bbox
    if not (west <= lon <= east and south <= lat <= north):
        raise ValueError("The reference point must lie inside the bounding box.")
    corners = [(west, south), (west, north), (east, south), (east, north)]
    return max(haversine_m(lon, lat, x, y) for x, y in corners) / METRES_PER_NAUTICAL_MILE
