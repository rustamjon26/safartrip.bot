from django.db import models

class Partner(models.Model):
    telegram_id = models.BigIntegerField(unique=True)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)

    def __str__(self):
        return self.name


class Object(models.Model):
    TYPE_CHOICES = (
        ('hotel', 'Mehmonxona'),
        ('dacha', 'Dacha'),
        ('house', 'Milliy uy'),
    )

    partner = models.ForeignKey(Partner, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    price = models.IntegerField()
    capacity = models.IntegerField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title


class Booking(models.Model):
    STATUS = (
        ('pending', 'Kutilmoqda'),
        ('approved', 'Tasdiqlandi'),
        ('cancelled', 'Bekor qilindi'),
    )

    obj = models.ForeignKey(Object, on_delete=models.CASCADE)
    client_name = models.CharField(max_length=100)
    client_phone = models.CharField(max_length=20)
    date_from = models.DateField()
    date_to = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS, default='pending')
