# hotels_data.py

HOTELS = [
    {"id": "h1", "name": "SUFFA 2400", "price": "450 000 so'm/kecha", "photos": [
        "AgACAgIAAxkBAAICuGl3gt11Jd7OGF9uIEArwRYYjFhXAAIVDGsbpaiAS1ES1qfXiYWSAQADAgADdwADOAQ",
        "AgACAgIAAxkBAAICuml3gvBQ3ZlENWgVeDyxpeVEs3uHAAIUDGsbpaiASzpKbMpDfL0VAQADAgADdwADOAQ",
        "AgACAgIAAxkBAAICvGl3gwR3kSXEWjrnUiJYE2xgNWjrAAIODGsbpaiAS4Q_272LHffnAQADAgADdwADOAQ",
    ]},
    {"id": "h2", "name": "ZAMINDOR Resort",       "price": "390 000 so'm/kecha", "photos": [
        "AgACAgIAAxkBAAICvml3gzrHAtWdwYiOuyGCIMTw0juLAALzC2sbpaiAS6k12wu0mmpWAQADAgADdwADOAQ",
        "AgACAgIAAxkBAAICwGl3g07N1eZ2sJa2i58e6d8fPC-PAAL0C2sbpaiAS2rkyidTGuvUAQADAgADdwADOAQ",
    ]},
    {"id": "h3", "name": "River Inn",       "price": "320 000 so'm/kecha", "photos": [
        "AgACAgIAAxkBAAICwml3g6jDBlpHtWxyRy4csh4sytmqAALoC2sbpaiASyYHbUkilyM0AQADAgADdwADOAQ",
    ]},
    {"id": "h4", "name": "Grand Palace",    "price": "520 000 so'm/kecha", "photos": [
        "AgACAgIAAxkBAAICxml3g9DESAipx_F4BmUGp3RC3SJoAAIZEWsbpah4S2R8g-HMqIQGAQADAgADdwADOAQ",
        "AgACAgIAAxkBAAICyGl3g-Vv8JwLjlofMb4SWugC8erKAAIYEWsbpah4SysTiqrw3Jl0AQADAgADdwADOAQ",
    ]},
    {"id": "h5", "name": "City Comfort",    "price": "280 000 so'm/kecha", "photos": [
        "AgACAgIAAxkBAAICyml3g_Wq2TaysVKYcwKg-YbFK4udAAIREWsbpah4S2tXsqzcXj_jAQADAgADdwADOAQ",
        "AgACAgIAAxkBAAICzGl3hAPn_98HTKUfhgk9KNRX3AGDAAIPEWsbpah4S5mNI_pzhukMAQADAgADdwADOAQ",
    ]},
    {"id": "h6", "name": "Snow Valley",     "price": "610 000 so'm/kecha", "photos": [
        "AgACAgIAAxkBAAICzml3hB7tLuWLQLDE5AbpQXEk8h6rAAIKDGsbpaiAS89CrYBQBhFnAQADAgADdwADOAQ",
    ]},
]

def find_hotel(hotel_id: str):
    for h in HOTELS:
        if h["id"] == hotel_id:
            return h
    return None
