# Fuel Route Optimizer

A high-performance Django REST API that determines the most cost-effective fuel stops along any road trip across the United States. Given a start and destination city, it generates the full driving route as GeoJSON and computes the mathematically optimal refuel stops to minimize total trip expense.

---

## Features

- **Optimal Fuel Stop Planning**: Implements a greedy "nearest cheaper or fill-up" algorithm that is provably optimal for single-rate linear fuel pricing.
- **Route & Geometry Generation**: Integrates with the open-source OSRM routing engine to fetch real-world driving paths and distances.
- **Full GeoJSON Output**: Provides a complete `FeatureCollection` containing both the polyline driving path and point markers for each suggested fuel stop.
- **Efficient Spatial Filtering**: Leverages vectorized NumPy haversine formulas to quickly filter candidate stations within a 10-mile corridor along the route.
- **Realistic Vehicle Constraints**: Configured for a 500-mile vehicle range, 10 MPG fuel economy (50-gallon tank capacity), and begins the journey with a full tank.

---

## Tech Stack

| Component | Choice | Rationale |
| :--- | :--- | :--- |
| **Web Framework** | Django + Django REST Framework | Robust API serialization, routing, and ORM support |
| **Routing Engine** | OSRM Driving API | Fast, keyless road network routing with GeoJSON polyline output |
| **Geocoding** | Nominatim (via `geopy`) | Reliable geocoding for trip endpoints (2 calls per request) |
| **Station Coordinates** | SimpleMaps US Cities Database | Offline mapping joined on `(city, state)` to eliminate live geocoding latency |
| **Spatial Filtering** | NumPy Vectorized Haversine | High-throughput distance calculations along complex route polylines |
| **Optimization** | Greedy Lookahead Algorithm | Polynomial time complexity with guaranteed minimal fuel expense |

---

## Quick Start

### 1. Prerequisites
- Python 3.10+
- Git

### 2. Clone and Setup Environment

```bash
git clone <your-repo-url>
cd spotter_ai_task

# Create and activate virtual environment
python -m venv .venv

# On Linux / macOS:
source .venv/bin/activate

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Windows (CMD):
.venv\Scripts\activate.bat

# Install dependencies
pip install -r requirements.txt
```

### 3. Database & Station Data Setup

Apply migrations and load the station data. You can either load the pre-built fixture (recommended for speed) or run the data import commands directly:

#### Option A: Load Fixture (Fastest)
```bash
python manage.py migrate
python manage.py loaddata fuel/fixtures/fuel_data.json
```

#### Option B: Fresh Import from CSVs
```bash
python manage.py migrate
python manage.py import_fuel_prices fuel-prices-for-be-assessment.csv
python manage.py geocode_stations uscities.csv
```

### 4. Run the Development Server

```bash
python manage.py runserver
```

The API will be available at `http://127.0.0.1:8000/`.

---

## API Reference

### Plan Route & Fuel Stops

Calculates the optimal fuel stops and driving route between two points in the USA.

- **Endpoint:** `POST /api/route-fuel/`
- **Content-Type:** `application/json`

#### Request Body

```json
{
  "start": "Los Angeles, CA",
  "finish": "New York, NY"
}
```

#### Example cURL

```bash
curl -X POST http://127.0.0.1:8000/api/route-fuel/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Los Angeles, CA", "finish": "New York, NY"}'
```

#### Response Payload

```json
{
  "start": "Los Angeles, CA",
  "finish": "New York, NY",
  "total_distance_miles": 2793.6,
  "vehicle": {
    "mpg": 10,
    "max_range_miles": 500
  },
  "total_fuel_cost_usd": 692.78,
  "number_of_fuel_stops": 11,
  "fuel_stops": [
    {
      "name": "Maverik #674",
      "opis_id": 12345,
      "lat": 35.1983,
      "lon": -111.6513,
      "price": 3.2823,
      "gallons": 27.68,
      "cost": 90.86,
      "distance_from_start_miles": 276.8
    }
  ],
  "map_geojson": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "properties": { "type": "route" },
        "geometry": {
          "type": "LineString",
          "coordinates": [[-118.2437, 34.0522], ...]
        }
      },
      {
        "type": "Feature",
        "properties": {
          "type": "fuel_stop",
          "name": "Maverik #674",
          "price": 3.2823,
          "gallons": 27.68,
          "cost": 90.86
        },
        "geometry": {
          "type": "Point",
          "coordinates": [-111.6513, 35.1983]
        }
      }
    ]
  }
}
```

#### Response Fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `start` | string | Normalized or requested starting location |
| `finish` | string | Normalized or requested destination location |
| `total_distance_miles` | float | Total road driving distance in miles from OSRM |
| `vehicle` | object | Vehicle specifications (`mpg`: 10, `max_range_miles`: 500) |
| `total_fuel_cost_usd` | float | Total expenditure on fuel across all planned stops |
| `number_of_fuel_stops` | integer | Total count of planned fuel purchase stops |
| `fuel_stops` | array | Detailed list of fuel stops including price, gallons, cost, and coordinates |
| `map_geojson` | object | Valid GeoJSON `FeatureCollection` with the route `LineString` and stop `Point`s |

---

## Core Assumptions

1. **Initial Fuel Tank**: The vehicle departs with a full 50-gallon tank (providing 500 miles of range before the first required purchase).
2. **Vehicle Specifications**: Fixed at **10 MPG** with a maximum range of **500 miles** (tank capacity = 50 gallons).
3. **Station Pricing**: When multiple fuel price records exist for the same station in the dataset, the minimum price is selected.
4. **Route Corridor Buffer**: A station is eligible for stopping if its perpendicular/nearest distance is within **10 miles** of the route polyline.
5. **Geocoding Coverage**: Stations whose `(city, state)` cannot be mapped to the offline US cities dataset are excluded during the data preparation step.

---

## Algorithm Details

The fuel optimization solver executes the following pipeline:

1. **Offline Spatial Matching**:
   Station locations are mapped from `(city, state)` to coordinates using the SimpleMaps US Cities dataset.

2. **Polyline & Distance Computation**:
   A single request to OSRM retrieves the driving route coordinates and cumulative milestone distances along the polyline.

3. **Candidate Corridor Filtering**:
   Using vectorized NumPy calculations, each station's distance to every route segment is evaluated. Only stations within the 10-mile corridor are retained and projected onto their corresponding route milepost.

4. **Greedy Lookahead Walk**:
   Starting from mile marker 0 with a full tank (50 gallons):
   - Determine all forward reachable stations within the remaining vehicle range ($\le 500\text{ miles}$).
   - **Case 1 (Cheaper Station Ahead):** If any reachable station offers a cheaper price than the current location, purchase only enough fuel to reach the *first* cheaper station.
   - **Case 2 (Current Station is Cheapest):** If all reachable stations are more expensive, fill the tank to maximum capacity (50 gallons) and advance to the cheapest available station within reach.
   - Repeat until the destination is directly reachable without further refuels.
   - Fuel purchases smaller than a minimum threshold (5.0 gallons) are avoided unless strictly necessary to prevent run-outs.

5. **Fuel Balance Verification**:
   The algorithm satisfies fuel conservation:
   $$\text{Total Gallons Purchased} = \frac{\text{Total Distance (miles)}}{10\text{ MPG}} - 50\text{ gallons (initial tank)}$$

---

## Performance & Optimization

- **Minimal Network Round-Trips**: Exactly 1 OSRM call and 2 Nominatim calls per request. No external geocoding calls during station search.
- **Fast Station Search**: Filtered candidates are retrieved via a single annotated Django ORM query and processed using vectorized NumPy arrays.
- **Typical Response Times**: ~1.5 to 3.5 seconds for coast-to-coast cross-country routes (dominated primarily by third-party OSRM network transit).

---

## Future Enhancements

- **Geocode & Route Caching**: Cache coordinates for popular city pairs using Redis or Django cache framework to reduce Nominatim overhead.
- **Precomputed Spatial Indexing**: Build an R-tree / PostGIS spatial index on fuel station coordinates to eliminate linear polyline projection passes.
- **Interactive UI**: Add a lightweight Leaflet or Mapbox web interface to visually render the returned GeoJSON route and stop points interactively.

---

## Author

Built by **Yaduraj Singh Yadav** for the Spotter Backend Engineer Assessment.