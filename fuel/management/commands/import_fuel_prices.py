import csv
from django.core.management.base import BaseCommand
from fuel.models import FuelStation, FuelPrice

class Command(BaseCommand):
    help = 'Import fuel prices from CSV'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str)

    def handle(self, *args, **options):
        with open(options['csv_file'], newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                opis_id = int(row['OPIS Truckstop ID'])
                station, _ = FuelStation.objects.get_or_create(
                    opis_id=opis_id,
                    defaults={
                        'name': row['Truckstop Name'].strip(),
                        'address': row['Address'].strip(),
                        'city': row['City'].strip(),
                        'state': row['State'].strip(),
                        'rack_id': int(row['Rack ID']) if row['Rack ID'] else None,
                    }
                )
                # Update station info if needed
                station.name = row['Truckstop Name'].strip()
                station.address = row['Address'].strip()
                station.city = row['City'].strip()
                station.state = row['State'].strip()
                station.save()

                FuelPrice.objects.create(
                    station=station,
                    retail_price=row['Retail Price']
                )
        self.stdout.write(self.style.SUCCESS('CSV imported successfully'))