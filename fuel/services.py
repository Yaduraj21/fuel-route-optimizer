import requests
import numpy as np
from math import radians, sin, cos, sqrt, atan2
from geopy.geocoders import Nominatim
from django.db.models import Min
from .models import FuelStation

# Nominatim is fine for one-off geocoding of start/finish (2 calls per request)
_geocoder = Nominatim(user_agent="fuel_route_assessment (contact: yaddurajsy@gmail.com)", timeout=15)


def geocode_place(query):
    """Geocode a single place name (e.g. 'Los Angeles, CA')."""
    location = _geocoder.geocode(query, timeout=15)
    if not location:
        raise ValueError(f"Could not geocode: {query}")
    return location.latitude, location.longitude


def get_route(start, finish):
    """
    One call to OSRM. Returns geometry (GeoJSON) + coords + distance in miles.
    """
    lat1, lon1 = geocode_place(start)
    lat2, lon2 = geocode_place(finish)

    url = (
        f"http://router.project-osrm.org/route/v1/driving/"
        f"{lon1},{lat1};{lon2},{lat2}"
        f"?overview=full&geometries=geojson"
    )
    resp = requests.get(url, timeout=20)
    data = resp.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(f"OSRM error: {data}")

    route = data["routes"][0]
    coords = route["geometry"]["coordinates"]  # list of [lon, lat]
    distance_miles = route["distance"] * 0.000621371

    return {
        "geometry": route["geometry"],
        "coordinates": coords,
        "distance_miles": distance_miles,
    }


def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def find_optimal_fuel_stops(route_data,
                             max_range_miles=500.0,
                             mpg=10.0,
                             route_buffer_miles=10.0,
                             min_purchase_gallons=5.0):
    """
    Optimal fuel stop planner.

    Uses the classic "cheapest reachable next stop" greedy, computed with a
    backward pass so that at each station we know which station to aim for
    next. This guarantees the total gallons bought equals the total gallons
    burned (no missing fuel, no phantom mileage).
    """
    coords = route_data["coordinates"]
    total_dist = float(route_data["distance_miles"])

    # ---- 1. Build cumulative distance along the route polyline
    cum_dist = [0.0]
    for i in range(1, len(coords)):
        lon1, lat1 = coords[i - 1]
        lon2, lat2 = coords[i]
        cum_dist.append(cum_dist[-1] + haversine(lat1, lon1, lat2, lon2))
    cum_dist = np.array(cum_dist)

    route_lats = np.array([c[1] for c in coords])
    route_lons = np.array([c[0] for c in coords])

    # ---- 2. Find stations within `route_buffer_miles` of the route
    stations = (
        FuelStation.objects
        .filter(lat__isnull=False, lon__isnull=False)
        .annotate(min_price=Min("fuelprice__retail_price"))
    )

    candidates = []
    for st in stations:
        if st.min_price is None:
            continue
        lat1 = radians(st.lat)
        lon1 = radians(st.lon)
        lat2 = np.radians(route_lats)
        lon2 = np.radians(route_lons)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
        d = 3958.8 * 2 * np.arcsin(np.sqrt(a))
        idx = int(np.argmin(d))
        if d[idx] <= route_buffer_miles:
            candidates.append({
                "name": st.name,
                "opis_id": st.opis_id,
                "lat": st.lat,
                "lon": st.lon,
                "price": float(st.min_price),
                "route_mile": float(cum_dist[idx]),
            })

    candidates.sort(key=lambda x: x["route_mile"])

    capacity_gallons = max_range_miles / mpg  # 50

    # ---- 3. Node list: [Start] + stations + [Finish]
    # Start has a "free" full tank, so price = 0.0 (we've already paid for it)
    # Finish has price = 0.0 so "the next cheapest" always wins if reachable
    nodes = (
        [{"name": "Start", "opis_id": None, "lat": None, "lon": None,
          "price": 0.0, "route_mile": 0.0}]
        + candidates
        + [{"name": "Finish", "opis_id": None, "lat": None, "lon": None,
            "price": 0.0, "route_mile": total_dist}]
    )
    finish_idx = len(nodes) - 1

    # ---- 4. Backward pass: for each i, find `next_stop[i]` = index j>i such
    #          that nodes[j] is the *cheapest* station reachable from i.
    #          If the finish is reachable, target the finish.
    next_stop = [finish_idx] * len(nodes)
    for i in range(finish_idx - 1, -1, -1):
        # All j with route_mile in (i.route_mile, i.route_mile + full_range]
        best_j = None
        best_price = None
        for j in range(i + 1, finish_idx + 1):
            gap = nodes[j]["route_mile"] - nodes[i]["route_mile"]
            if gap > capacity_gallons * mpg:
                break
            # Reachable
            if j == finish_idx:
                # Prefer finish if reachable
                if best_j is None or best_j == finish_idx:
                    # keep it
                    best_j = j
                    best_price = 0.0
                break
            p = nodes[j]["price"]
            if best_price is None or p < best_price:
                best_price = p
                best_j = j
        next_stop[i] = best_j if best_j is not None else finish_idx

    # ---- 5. Forward pass: buy the minimum at each stop to reach next_stop
    purchases = []
    total_cost = 0.0
    fuel = capacity_gallons
    i = 0

    for _ in range(len(nodes) + 5):
        if i == finish_idx:
            break

        cur = nodes[i]
        full_range = capacity_gallons * mpg

        # All stations reachable on a full tank
        reachable = []
        for j in range(i + 1, finish_idx + 1):
            if nodes[j]["route_mile"] - cur["route_mile"] > full_range:
                break
            reachable.append(j)

        if not reachable:
            raise RuntimeError(f"Stranded at {cur['name']} (mile {cur['route_mile']:.1f})")

        # Is the finish reachable? Then we can (maybe) just drive there.
        if reachable[-1] == finish_idx and fuel * mpg >= total_dist - cur["route_mile"]:
            break

        # Find nearest strictly cheaper station within reach
        cheaper_j = None
        for j in reachable:
            if j == finish_idx:
                cheaper_j = j
                break
            if nodes[j]["price"] < cur["price"]:
                cheaper_j = j
                break

        if cheaper_j is not None:
            # Buy just enough to reach it
            target_idx = cheaper_j
            dist = nodes[target_idx]["route_mile"] - cur["route_mile"]
            needed = dist / mpg
            buy_gal = max(0.0, needed - fuel)
            buy_gal = min(buy_gal, capacity_gallons - fuel)
        else:
            # No cheaper station in reach → fill tank, drive to cheapest reachable
            target_idx = min(reachable, key=lambda j: nodes[j]["price"])
            buy_gal = capacity_gallons - fuel

        # Record purchase (if enough)
        if buy_gal >= min_purchase_gallons and cur["price"] > 0:
            cost = buy_gal * cur["price"]
            total_cost += cost
            fuel += buy_gal
            purchases.append({
                "name": cur["name"],
                "opis_id": cur["opis_id"],
                "lat": cur["lat"],
                "lon": cur["lon"],
                "price": round(cur["price"], 4),
                "gallons": round(buy_gal, 2),
                "cost": round(cost, 2),
                "distance_from_start_miles": round(cur["route_mile"], 1),
            })

        dist = nodes[target_idx]["route_mile"] - cur["route_mile"]
        fuel -= dist / mpg
        i = target_idx

    return purchases, round(total_cost, 2), round(total_dist, 1)