from django.db import models

class FuelStation(models.Model):
    opis_id = models.IntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, blank=True)
    rack_id = models.IntegerField(null=True, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state})"

class FuelPrice(models.Model):
    station = models.ForeignKey(FuelStation, on_delete=models.CASCADE, related_name='fuelprice')
    retail_price = models.DecimalField(max_digits=8, decimal_places=5)

    def __str__(self):
        return f"{self.station.name} - ${self.retail_price}"