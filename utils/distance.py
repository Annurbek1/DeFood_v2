from geopy.distance import geodesic
from config import Config

def check_delivery_distance(lat: float, lon: float) -> tuple[bool, float]:
    """
    Check if delivery is possible to given coordinates
    Returns: (is_deliverable: bool, distance: float)
    """
    user_location = (lat, lon)
    city_center = (Config.CITY_CENTER_LATITUDE, Config.CITY_CENTER_LONGITUDE)  # Access through Config class
    
    distance = geodesic(city_center, user_location).km
    is_deliverable = distance <= Config.MAX_DISTANCE_KM  # Access through Config class
    
    return is_deliverable, distance