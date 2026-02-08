from .models import Booking

def is_available(obj, date_from, date_to):
    return not Booking.objects.filter(
        obj=obj,
        date_from__lt=date_to,
        date_to__gt=date_from,
        status="approved"
    ).exists()
