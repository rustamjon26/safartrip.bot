"""
FSM States for booking flow
"""
from aiogram.fsm.state import State, StatesGroup


class BookingForm(StatesGroup):
    """States for the service booking flow."""
    
    # Step 1: Service type is already selected when entering FSM
    service = State()      # Which service user selected
    name = State()         # User's full name
    phone = State()        # Phone number (+998...)
    datetime = State()     # Preferred date and time
    details = State()      # Additional details/notes
    confirm = State()      # Final confirmation (HA/YO'Q)


class LanguageSelection(StatesGroup):
    """State for language selection flow."""
    
    choosing = State()     # User is choosing language


# =============================================================================
# Partner-based booking flows
# =============================================================================

class GuideBooking(StatesGroup):
    """FSM states for guide booking flow."""
    
    selecting_partner = State()  # User selecting a guide from list
    date = State()               # Date or date range
    route = State()              # Route/location
    people_count = State()       # Number of people
    note = State()               # Optional note
    confirm = State()            # Final confirmation


class TaxiBooking(StatesGroup):
    """FSM states for taxi booking flow."""
    
    selecting_partner = State()  # User selecting a taxi from list
    pickup_location = State()    # Pickup location
    dropoff_location = State()   # Dropoff location
    pickup_time = State()        # Pickup time
    passengers = State()         # Number of passengers
    note = State()               # Optional note
    confirm = State()            # Final confirmation

