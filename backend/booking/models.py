from django.db import models

class Partner(models.Model):
    telegram_id = models.BigIntegerField(unique=True)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    balance = models.IntegerField(default=0)

class Object(models.Model):
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    price = models.IntegerField()
    capacity = models.IntegerField()
    lat = models.FloatField()
    lon = models.FloatField()
    is_active = models.BooleanField(default=True)

class Booking(models.Model):
    STATUS = (
        ('pending','pending'),
        ('approved','approved'),
        ('cancelled','cancelled')
    )

    obj = models.ForeignKey(Object, on_delete=models.CASCADE)
    client_name = models.CharField(max_length=100)
    client_phone = models.CharField(max_length=20)
    date_from = models.DateField()
    date_to = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS, default='pending')
from . import signals
