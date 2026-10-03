import csv
import os
from django.core.management.base import BaseCommand
from fuel.models import FuelStation


class Command(BaseCommand):
    help = 'Load lat/lon from SimpleMaps uscities.csv (offline, no API calls)'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_path',
            type=str,
            help='Path to uscities.csv'
        )

    def handle(self, *args, **options):
        csv_path = options['csv_path']

        if not os.path.exists(csv_path):
            self.stdout.write(self.style.ERROR(f"File not found: {csv_path}"))
            return

        # Build lookup: (city_lower, state_lower) -> (lat, lon)
        lookup = {}
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                city = (row.get('city') or '').strip().lower()
                state = (row.get('state_id') or '').strip().lower()
                lat = row.get('lat')
                lon = row.get('lng')
                if not city or not state or not lat or not lon:
                    continue
                if (city, state) not in lookup:
                    try:
                        lookup[(city, state)] = (float(lat), float(lon))
                    except ValueError:
                        continue

        self.stdout.write(f"Loaded {len(lookup)} city/state pairs")

        # Update stations
        updated = 0
        missed = 0
        for station in FuelStation.objects.filter(lat__isnull=True):
            city = (station.city or '').strip().lower()
            state = (station.state or '').strip().lower()
            coords = lookup.get((city, state))
            if coords:
                station.lat, station.lon = coords
                station.save(update_fields=['lat', 'lon'])
                updated += 1
            else:
                missed += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Updated: {updated}, missed: {missed}"
        ))