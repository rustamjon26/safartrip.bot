from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Object, Booking
from .services import is_available

class BookingCreate(APIView):
    def post(self, request):
        obj = Object.objects.get(id=request.data["object_id"])
        if not is_available(obj, request.data["date_from"], request.data["date_to"]):
            return Response({"error":"Band"}, status=400)

        booking = Booking.objects.create(
            obj=obj,
            client_name=request.data["name"],
            client_phone=request.data["phone"],
            date_from=request.data["date_from"],
            date_to=request.data["date_to"]
        )
        return Response({"id": booking.id})
