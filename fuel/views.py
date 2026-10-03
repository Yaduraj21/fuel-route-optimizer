from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .services import get_route, find_optimal_fuel_stops


class RouteFuelView(APIView):
    def post(self, request):
        start = request.data.get("start")
        finish = request.data.get("finish")

        if not start or not finish:
            return Response(
                {"error": "Both 'start' and 'finish' are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            route_data = get_route(start, finish)
            purchases, total_cost, total_distance = find_optimal_fuel_stops(route_data)

            # Build a simple FeatureCollection for map preview
            features = [
                {
                    "type": "Feature",
                    "properties": {"type": "route"},
                    "geometry": route_data["geometry"],
                }
            ]
            for p in purchases:
                if p["lat"] is None or p["lon"] is None:
                    continue
                features.append({
                    "type": "Feature",
                    "properties": {
                        "type": "fuel_stop",
                        "name": p["name"],
                        "price": p["price"],
                        "gallons": p["gallons"],
                        "cost": p["cost"],
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [p["lon"], p["lat"]],
                    },
                })

            return Response({
                "start": start,
                "finish": finish,
                "total_distance_miles": total_distance,
                "vehicle": {"mpg": 10, "max_range_miles": 500},
                "total_fuel_cost_usd": total_cost,
                "number_of_fuel_stops": len(purchases),
                "fuel_stops": purchases,
                "map_geojson": {"type": "FeatureCollection", "features": features},
            })

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)