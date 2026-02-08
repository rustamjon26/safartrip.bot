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
